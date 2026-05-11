#!/usr/bin/env python3
"""
Fetch a single Common Crawl WARC record (by JSONL line input) and save the
HTTP response body to recovered_alt/itforchange.net/<path>.

Reads ONE JSON record from argv[1] (a single line from cc_captures.jsonl),
issues a Range request to data.commoncrawl.org, decompresses the gzip WARC
fragment, splits off WARC + HTTP headers, and writes the body.

Usage (single):
    ./cc_fetch.py '<json-line>'

Usage (bulk):
    cat data/cc_captures.jsonl | xargs -d '\n' -P 4 -I{} ./cc_fetch.py '{}'
"""
import gzip
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT_ROOT = Path(os.environ.get('OUT_ROOT', 'recovered_alt/itforchange.net'))
WAYBACK_ROOT = Path(os.environ.get('WAYBACK_ROOT', 'recovered/itforchange.net'))
LOG_DIR = Path(os.environ.get('LOG_DIR', 'logs'))
UA = 'Mozilla/5.0 (compatible; archive-ingest/1.0; +itfc)'
TIMEOUT = 60


def url_to_path(url: str, mime: str) -> Path:
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
    if '/resources/resources/' in rel:
        raise ValueError('refused: recursive path')
    rel = urllib.parse.unquote(rel.split('?', 1)[0])
    last = rel.rstrip('/').rsplit('/', 1)[-1]
    if mime == 'text/html':
        if rel.endswith('/'):
            rel = rel + 'index.html'
        elif '.' not in last:
            rel = rel.rstrip('/') + '.html'
    elif '.' not in last:
        rel = rel + '.bin'
    return OUT_ROOT / rel


def fetch_warc_range(warc_filename: str, offset: int, length: int) -> bytes | None:
    url = f'https://data.commoncrawl.org/{warc_filename}'
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Range': f'bytes={offset}-{offset + length - 1}',
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            chunk = r.read()
    except Exception as e:
        return None
    try:
        decompressed = gzip.decompress(chunk)
    except Exception:
        return None
    # WARC record: WARC headers \r\n\r\n HTTP headers \r\n\r\n body
    parts = decompressed.split(b'\r\n\r\n', 2)
    if len(parts) < 3:
        return None
    return parts[2]


def log_ok(rec: dict, out_path: Path) -> None:
    with (LOG_DIR / 'cc_ok.log').open('a') as f:
        f.write(f"{rec['url']}\t{rec['timestamp']}\t{out_path}\n")


def log_fail(rec: dict, reason: str) -> None:
    with (LOG_DIR / 'cc_failed.log').open('a') as f:
        f.write(f"{reason}\t{rec['url']}\t{rec.get('timestamp', '')}\n")


def main(line: str) -> int:
    try:
        rec = json.loads(line)
    except json.JSONDecodeError as e:
        print(f'bad json: {e}', file=sys.stderr)
        return 2

    url = rec.get('url', '')
    if not url:
        log_fail(rec, 'no-url')
        return 1
    try:
        out_path = url_to_path(url, rec.get('mime', ''))
    except ValueError as e:
        log_fail(rec, str(e))
        return 1

    # Skip only if alt tree already has this exact file — duplication with
    # Wayback is acceptable here (user requested it for cross-comparison).
    if out_path.exists() and out_path.stat().st_size > 0:
        return 0

    body = fetch_warc_range(rec['warc_filename'], rec['offset'], rec['length'])
    if body is None or len(body) < 100:
        log_fail(rec, 'fetch-failed-or-empty')
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(body)
    log_ok(rec, out_path)
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: cc_fetch.py \'<json-line>\'', file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
