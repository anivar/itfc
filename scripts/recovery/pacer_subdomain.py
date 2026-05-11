#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "httpx[http2]>=0.28",
# ]
# ///
"""Generic Wayback HTTP/2 pacer (host-agnostic fork of wb_h2_pacer.py).

Reads TSV (timestamp\tmime\turl) from stdin. Saves to OUT_ROOT preserving
the URL host directory layout (so multiple subdomains can share the same
parent dir with no path collisions).

Env vars (all required except UA / RATE_INITIAL):
  OUT_ROOT        — root directory for saved bodies (e.g. /.../subdomains/projects/htdocs)
  HOST            — single hostname this pacer is restricted to (rejects everything else)
  LOG_PREFIX      — prefix for log file names (e.g. "projects")
  LOG_DIR         — where to write the three log files
  RATE_INITIAL    — starting AIMD rate in req/s (default 0.5)
  CONCURRENCY     — max in-flight on the H/2 connection (default 6)
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

OUT_ROOT = Path(os.environ['OUT_ROOT'])
HOST = os.environ['HOST'].lower()
LOG_DIR = Path(os.environ.get('LOG_DIR', 'logs/pacer'))
LOG_PREFIX = os.environ.get('LOG_PREFIX', HOST.split('.')[0])
UA = os.environ.get('UA', 'Mozilla/5.0 (compatible; site-mirror/2.0-h2)')

INITIAL_RATE = float(os.environ.get('RATE_INITIAL', '0.5'))
MIN_RATE = 0.2
MAX_RATE = 5.0
ADD_INC = 0.1
AIMD_WINDOW = 50
MD_FACTOR = 0.5
CONCURRENCY = int(os.environ.get('CONCURRENCY', '6'))
ATTEMPTS = 3
PER_REQ_TIMEOUT = 60.0


def url_to_path(url: str) -> Path | None:
    """Map URL → OUT_ROOT/<path-without-host>. Restricts to HOST."""
    rel = url
    for prefix in ('http://', 'https://'):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
    host, _, path = rel.partition('/')
    host = host.lower().split(':', 1)[0]
    if host != HOST:
        return None
    if not path:
        path = 'index'
    path = urllib.parse.unquote(path.split('?', 1)[0])
    last = path.rstrip('/').rsplit('/', 1)[-1]
    if path.endswith('/'):
        path = path + 'index.html'
    elif '.' not in last:
        path = path + '.html'
    # Defensive: collapse repeated identical path components
    if re.search(r'/([^/]+)/\1/', path):
        return None
    return OUT_ROOT / path


class Pacer:
    def __init__(self) -> None:
        self.rate = INITIAL_RATE
        self.successes = 0
        self.last_dispatch = 0.0
        self._lock = asyncio.Lock()
        self.log = (LOG_DIR / f'{LOG_PREFIX}_pacer.log').open('a')
        self.log.write(f'\n=== {time.strftime("%Y-%m-%d %H:%M:%S")} pacer start host={HOST} rate={self.rate}\n')
        self.log.flush()

    async def gate(self) -> None:
        async with self._lock:
            now = time.monotonic()
            interval = 1.0 / max(self.rate, 0.01)
            wait = (self.last_dispatch + interval) - now
            if wait > 0:
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
                self.log.write(f'AI {old:.2f} -> {self.rate:.2f}\n'); self.log.flush()

    def on_throttle(self, reason: str) -> None:
        old = self.rate
        self.rate = max(MIN_RATE, self.rate * MD_FACTOR)
        self.successes = 0
        self.log.write(f'MD {old:.2f} -> {self.rate:.2f}  ({reason})\n'); self.log.flush()


def ensure_parent_is_dir(path: Path) -> None:
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
    ensure_parent_is_dir(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.is_dir():
        out_path = out_path / 'index.html'
    out_path.write_bytes(data)


async def fetch_one(client, pacer, ts, url, out_path, ok_log, fail_log):
    wb_url = f'https://web.archive.org/web/{ts}id_/{url}'
    last_code = '000'
    for attempt in range(1, ATTEMPTS + 1):
        await pacer.gate()
        try:
            r = await client.get(wb_url, timeout=PER_REQ_TIMEOUT, follow_redirects=True)
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

    jobs = []
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
            skipped += 1
            continue
        jobs.append((ts, url, str(out_path)))

    print(f'[{LOG_PREFIX}] queued={len(jobs)} skipped={skipped}', file=sys.stderr)
    if not jobs:
        return 0

    pacer = Pacer()
    sem = asyncio.Semaphore(CONCURRENCY)
    ok_log = (LOG_DIR / f'{LOG_PREFIX}_ok.log').open('a')
    fail_log = (LOG_DIR / f'{LOG_PREFIX}_failed.log').open('a')

    limits = httpx.Limits(max_keepalive_connections=1, max_connections=1, keepalive_expiry=300.0)
    headers = {'User-Agent': UA, 'Accept-Encoding': 'gzip, deflate, br'}

    async with httpx.AsyncClient(http2=True, http1=False, limits=limits,
                                  headers=headers, follow_redirects=True) as client:
        try:
            r0 = await client.get('https://web.archive.org/', timeout=20)
            print(f'[{LOG_PREFIX}] warm proto={r0.http_version} status={r0.status_code}', file=sys.stderr)
        except Exception as e:
            print(f'[{LOG_PREFIX}] warm failed: {e!r}', file=sys.stderr)

        progress = {'ok': 0, 'fail': 0}
        progress_lock = asyncio.Lock()
        t0 = time.time()

        async def worker(ts, url, out_str):
            async with sem:
                result = await fetch_one(client, pacer, ts, url, Path(out_str), ok_log, fail_log)
            async with progress_lock:
                progress[result] += 1
                done = progress['ok'] + progress['fail']
                if done % 25 == 0:
                    elapsed = time.time() - t0
                    rate = done / max(elapsed, 1) * 60
                    print(f'[{LOG_PREFIX}] {done}/{len(jobs)}  ok={progress["ok"]} '
                          f'fail={progress["fail"]}  {rate:.1f}/min  '
                          f'pace={pacer.rate:.2f}r/s', file=sys.stderr)

        await asyncio.gather(*(worker(ts, url, p) for ts, url, p in jobs))

    print(f'[{LOG_PREFIX}] done ok={progress["ok"]} fail={progress["fail"]} '
          f'final_rate={pacer.rate:.2f}r/s', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
