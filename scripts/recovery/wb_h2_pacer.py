#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "httpx[http2]>=0.28",
# ]
# ///
"""Wayback fetcher v2 — single HTTP/2 connection + AIMD pacing.

Reads TSV lines (timestamp\tmime\turl) from stdin, fetches
https://web.archive.org/web/<ts>id_/<url> over a single persistent HTTP/2
connection, and saves bodies under recovered/itforchange.net/<path>.

Why single-connection: Wayback's content envelope appears to throttle on
TCP-connection establishment rate, not request rate. Empirically, fresh
sockets to web.archive.org:443 from this IP get refused while existing
worker connections succeed. A single multiplexed H/2 connection avoids
re-paying the connect cost.

Why AIMD: the sustained ceiling is unknown. Start at 0.5 req/s,
additive-increase by +0.1 req/s per 50 successes, multiplicative-decrease
(halve) on any 429/503/connect-refusal. Same control law as TCP Reno
because the underlying constraint is structurally identical.

Concurrency: a small pool of in-flight requests on the H/2 stream (default
8) so the pacer can saturate the allowed rate without blocking on RTT.

Logs:
  logs/h2_ok.log       OK   <ts> <url>
  logs/h2_failed.log   FAIL <code> <ts> <url>
  logs/h2_pacer.log    rate decisions, AIMD events
"""
from __future__ import annotations

import asyncio
import os
import random
import re
import sys
import time
import urllib.parse
from pathlib import Path

import httpx

OUT_ROOT = Path(os.environ.get('OUT_ROOT', 'recovered/itforchange.net'))
LOG_DIR = Path(os.environ.get('LOG_DIR', 'logs'))
UA = 'Mozilla/5.0 (compatible; archive-ingest/2.0-h2; +itfc)'

# AIMD knobs
INITIAL_RATE = 0.5            # req/s
MIN_RATE = 0.2
MAX_RATE = 5.0
ADD_INC = 0.1                 # +req/s per AIMD_WINDOW successes
AIMD_WINDOW = 50              # successes between AIs
MD_FACTOR = 0.5               # halve on throttle
CONCURRENCY = 8               # max in-flight on the single H/2 connection
ATTEMPTS = 3
PER_REQ_TIMEOUT = 60.0


def url_to_path(url: str) -> Path | None:
    rel = url
    for prefix in ('http://', 'https://'):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
    if rel.startswith('www.'):
        rel = rel[4:]
    for prefix in ('itforchange.net:80/', 'itforchange.net:443/', 'itforchange.net/'):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
            break
    if rel in ('itforchange.net', 'itforchange.net:80', 'itforchange.net:443', ''):
        rel = 'index'
    if re.search(r'/([^/]+)/\1/', rel):
        return None
    rel = urllib.parse.unquote(rel.split('?', 1)[0])
    last = rel.rstrip('/').rsplit('/', 1)[-1]
    if rel.endswith('/'):
        rel = rel + 'index.html'
    elif '.' not in last:
        rel = rel + '.html'
    return OUT_ROOT / rel


class Pacer:
    """Token-bucket-ish AIMD pacer. Single coroutine sleeps between dispatches."""

    def __init__(self) -> None:
        self.rate = INITIAL_RATE
        self.successes = 0
        self.last_dispatch = 0.0
        self._lock = asyncio.Lock()
        self.log = (LOG_DIR / 'h2_pacer.log').open('a')
        self.log.write(f'\n=== {time.strftime("%Y-%m-%d %H:%M:%S")} pacer start rate={self.rate}\n')
        self.log.flush()

    async def gate(self) -> None:
        """Block until the next dispatch slot."""
        async with self._lock:
            now = time.monotonic()
            interval = 1.0 / max(self.rate, 0.01)
            wait = (self.last_dispatch + interval) - now
            if wait > 0:
                # Tiny ±20% jitter on dispatch interval too
                wait *= 0.8 + random.random() * 0.4
                await asyncio.sleep(wait)
            self.last_dispatch = time.monotonic()

    def on_success(self) -> None:
        self.successes += 1
        if self.successes >= AIMD_WINDOW:
            self.successes = 0
            old = self.rate
            self.rate = min(MAX_RATE, self.rate + ADD_INC)
            if self.rate != old:
                self.log.write(f'AI {old:.2f} -> {self.rate:.2f}\n')
                self.log.flush()

    def on_throttle(self, reason: str) -> None:
        old = self.rate
        self.rate = max(MIN_RATE, self.rate * MD_FACTOR)
        self.successes = 0
        self.log.write(f'MD {old:.2f} -> {self.rate:.2f}  ({reason})\n')
        self.log.flush()


def ensure_parent_is_dir(path: Path) -> None:
    """Walk up `path`; if any ancestor is currently a file, convert it into a
    directory by moving it to <name>/index.html. Drupal alias / clean URLs
    yield collisions like /index.php/gender (saved earlier as a file) and
    /index.php/gender/foo (now needing /index.php/gender as a parent dir)."""
    parts = path.parts
    cur = Path(parts[0])
    for part in parts[1:-1]:
        cur = cur / part
        if cur.is_file():
            tmp = cur.with_suffix(cur.suffix + '.__movetmp')
            cur.rename(tmp)
            cur.mkdir(parents=True, exist_ok=True)
            tmp.rename(cur / 'index.html')


def safe_write(out_path: Path, data: bytes) -> None:
    """Write `data` to `out_path`, resolving file/dir collisions both directions:
    - parent path occupied by a file → convert to dir-with-index.html
    - target path occupied by a directory → write to <path>/index.html"""
    ensure_parent_is_dir(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.is_dir():
        out_path = out_path / 'index.html'
    out_path.write_bytes(data)


async def fetch_one(client: httpx.AsyncClient, pacer: Pacer, ts: str, url: str,
                    out_path: Path, ok_log, fail_log) -> str:
    wb_url = f'https://web.archive.org/web/{ts}id_/{url}'
    last_code = '000'
    for attempt in range(1, ATTEMPTS + 1):
        await pacer.gate()
        try:
            r = await client.get(wb_url, timeout=PER_REQ_TIMEOUT,
                                 follow_redirects=True)
            last_code = str(r.status_code)
        except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
            last_code = f'cx-{type(e).__name__}'
            pacer.on_throttle(f'connect: {type(e).__name__}')
            await asyncio.sleep(2 ** attempt + random.random() * 2)
            continue
        except httpx.TimeoutException:
            last_code = 'timeout'
            await asyncio.sleep(2 ** attempt + random.random() * 2)
            continue
        except Exception as e:
            last_code = f'err-{type(e).__name__}'
            await asyncio.sleep(2 ** attempt + random.random() * 2)
            continue

        if r.status_code == 200 and r.content:
            try:
                safe_write(out_path, r.content)
            except OSError as e:
                last_code = f'io-{type(e).__name__}'
                fail_log.write(f'FAIL {last_code} {ts} {url}\n'); fail_log.flush()
                return 'fail'
            pacer.on_success()
            ok_log.write(f'OK   {ts} {url}\n'); ok_log.flush()
            return 'ok'

        if r.status_code in (429, 503, 502, 504):
            pacer.on_throttle(f'http {r.status_code}')
            await asyncio.sleep(2 ** attempt + random.random() * 4)
            continue

        if 400 <= r.status_code < 500:
            break

    fail_log.write(f'FAIL {last_code} {ts} {url}\n'); fail_log.flush()
    return 'fail'


async def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # REFRESH=1 → ignore the on-disk skip cache and always re-fetch.
    # REFRESH_NEWER=1 → only re-fetch when the input ts is newer than the
    # local file's mtime (so an older Wayback capture won't clobber a
    # newer one we already have).
    refresh = os.environ.get('REFRESH') == '1'
    refresh_newer = os.environ.get('REFRESH_NEWER') == '1'

    # Read all input first so we can shuffle / report progress
    jobs: list[tuple[str, str, str]] = []
    skipped = 0
    for line in sys.stdin:
        line = line.rstrip('\n')
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) != 3:
            continue
        ts, mime, url = parts
        out_path = url_to_path(url)
        if out_path is None:
            skipped += 1
            continue
        if out_path.exists() and out_path.stat().st_size > 0:
            if refresh:
                pass  # always overwrite
            elif refresh_newer:
                # ts is YYYYMMDDhhmmss; convert to epoch
                try:
                    cap_epoch = time.mktime(time.strptime(ts[:14], '%Y%m%d%H%M%S'))
                except ValueError:
                    cap_epoch = 0
                if cap_epoch <= out_path.stat().st_mtime:
                    skipped += 1
                    continue
            else:
                skipped += 1
                continue
        jobs.append((ts, url, str(out_path)))

    print(f'[h2-pacer] queued={len(jobs)} skipped={skipped}', file=sys.stderr)
    if not jobs:
        return 0

    pacer = Pacer()
    sem = asyncio.Semaphore(CONCURRENCY)
    ok_log = (LOG_DIR / 'h2_ok.log').open('a')
    fail_log = (LOG_DIR / 'h2_failed.log').open('a')

    limits = httpx.Limits(max_keepalive_connections=1, max_connections=1,
                          keepalive_expiry=300.0)
    headers = {'User-Agent': UA, 'Accept-Encoding': 'gzip, deflate, br'}

    async with httpx.AsyncClient(http2=True, http1=False, limits=limits,
                                  headers=headers, follow_redirects=True) as client:
        # Warm the connection
        try:
            r0 = await client.get('https://web.archive.org/', timeout=20)
            print(f'[h2-pacer] warm proto={r0.http_version} status={r0.status_code}',
                  file=sys.stderr)
        except Exception as e:
            print(f'[h2-pacer] warm failed: {e!r} — proceeding anyway', file=sys.stderr)

        progress = {'ok': 0, 'fail': 0}
        progress_lock = asyncio.Lock()
        t0 = time.time()

        async def worker(ts: str, url: str, out_str: str) -> None:
            async with sem:
                result = await fetch_one(client, pacer, ts, url, Path(out_str),
                                         ok_log, fail_log)
            async with progress_lock:
                progress[result] += 1
                done = progress['ok'] + progress['fail']
                if done % 25 == 0:
                    elapsed = time.time() - t0
                    rate = done / max(elapsed, 1) * 60
                    print(f'[h2-pacer] {done}/{len(jobs)}  ok={progress["ok"]} '
                          f'fail={progress["fail"]}  {rate:.1f}/min  '
                          f'pace={pacer.rate:.2f}r/s', file=sys.stderr)

        await asyncio.gather(*(worker(ts, url, p) for ts, url, p in jobs))

    print(f'[h2-pacer] done ok={progress["ok"]} fail={progress["fail"]} '
          f'final_rate={pacer.rate:.2f}r/s', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
