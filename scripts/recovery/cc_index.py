#!/usr/bin/env python3
"""
Bulk-query Common Crawl CDX indexes for all itforchange.net captures.

Walks the N most-recent monthly indexes (default: 24 = ~2 years) and writes
unique (url, digest) pairs to data/cc_captures.jsonl with WARC location info
needed to fetch the actual content.

Output JSONL fields:
    url, timestamp, status, mime, digest, warc_filename, offset, length

Usage:
    ./cc_index.py [--indexes N]
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

DATA_DIR = Path(os.environ.get('DATA_DIR', 'data'))
LOG_DIR = Path(os.environ.get('LOG_DIR', 'logs'))
DOMAIN_QUERY = 'itforchange.net/*'
UA = 'Mozilla/5.0 (compatible; archive-ingest/1.0; +itfc)'


def http_get_text(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')


def query_index(cdx_api: str) -> list[dict]:
    """Query one CC monthly index for all itforchange.net URLs.
    Retries on 503/504 with exponential backoff."""
    q = f'{cdx_api}?url={DOMAIN_QUERY}&output=json'
    body = None
    for attempt in range(4):
        try:
            body = http_get_text(q, timeout=120)
            break
        except urllib.error.HTTPError as e:
            if e.code in (503, 504, 429) and attempt < 3:
                time.sleep((attempt + 1) * 8)
                continue
            print(f'  err {cdx_api.rsplit("/", 1)[1]}: {e}', file=sys.stderr)
            return []
        except Exception as e:
            if attempt < 3:
                time.sleep((attempt + 1) * 5)
                continue
            print(f'  err {cdx_api.rsplit("/", 1)[1]}: {e}', file=sys.stderr)
            return []
    if body is None:
        return []
    out = []
    for line in body.splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get('status') != '200':
            continue
        out.append({
            'url': rec.get('url', ''),
            'timestamp': rec.get('timestamp', ''),
            'status': rec.get('status', ''),
            'mime': rec.get('mime-detected') or rec.get('mime', ''),
            'digest': rec.get('digest', ''),
            'warc_filename': rec.get('filename', ''),
            'offset': int(rec.get('offset', 0)),
            'length': int(rec.get('length', 0)),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--indexes', type=int, default=24,
                    help='How many most-recent monthly indexes to query (default 24)')
    ap.add_argument('--workers', type=int, default=4,
                    help='Parallel index queries (default 4)')
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)

    print('fetching CC index list...', file=sys.stderr)
    info = json.loads(http_get_text('https://index.commoncrawl.org/collinfo.json', 30))
    selected = info[: args.indexes]
    print(f'querying {len(selected)} indexes in parallel (workers={args.workers})', file=sys.stderr)

    seen: dict[tuple[str, str], dict] = {}  # (url, digest) → record
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(query_index, idx['cdx-api']): idx['id'] for idx in selected}
        for fut in as_completed(futs):
            cdx_id = futs[fut]
            try:
                recs = fut.result()
            except Exception as e:
                print(f'  err {cdx_id}: {e}', file=sys.stderr)
                continue
            new = 0
            for r in recs:
                key = (r['url'], r['digest'])
                if key not in seen:
                    seen[key] = r
                    new += 1
            print(f'  {cdx_id}: +{new} new (total unique {len(seen)})',
                  file=sys.stderr)

    out_path = DATA_DIR / 'cc_captures.jsonl'
    with out_path.open('w') as f:
        for r in seen.values():
            f.write(json.dumps(r) + '\n')
    print(f'\nwrote {len(seen)} unique captures → {out_path}', file=sys.stderr)
    print(f'elapsed: {time.time() - t0:.0f}s', file=sys.stderr)


if __name__ == '__main__':
    main()
