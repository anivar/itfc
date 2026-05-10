#!/usr/bin/env python3
"""Split pages.json into N shards under src/data/pages/.

Each shard holds an array of page entries assigned via stable hash on
the slug, so the same slug always lands in the same shard across runs
(diff churn stays local). After running, src/data/pages.json is
deleted; the loader (`src/lib/pages.ts`) globs the shards.

Idempotent. Pass --apply to write.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_JSON = ROOT / 'src' / 'data' / 'pages.json'
SHARDS_DIR = ROOT / 'src' / 'data' / 'pages'


def shard_for(slug: str, n: int) -> int:
    h = hashlib.sha1(slug.encode('utf-8', 'replace')).digest()
    return int.from_bytes(h[:4], 'big') % n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--shards', type=int, default=8)
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    pages = json.loads(PAGES_JSON.read_text())
    buckets: dict[int, list[dict]] = defaultdict(list)
    for p in pages:
        buckets[shard_for(p['slug'], args.shards)].append(p)

    sizes = []
    for i in range(args.shards):
        body = json.dumps(buckets[i], ensure_ascii=False, separators=(',', ':'))
        sizes.append((i, len(buckets[i]), len(body)))

    print(f'pages: {len(pages)}  shards: {args.shards}')
    print(f'  {"#":>2}  {"pages":>5}  {"bytes":>10}  {"MB":>5}')
    for i, n, sz in sizes:
        print(f'  {i:2d}  {n:5d}  {sz:10d}  {sz/1024/1024:5.1f}')
    print(f'\ntotal bytes (sum of shards): '
          f'{sum(s for _,_,s in sizes)/1024/1024:.1f} MB')

    if args.apply:
        if SHARDS_DIR.exists():
            shutil.rmtree(SHARDS_DIR)
        SHARDS_DIR.mkdir(parents=True)
        for i in range(args.shards):
            (SHARDS_DIR / f'{i:02d}.json').write_text(
                json.dumps(buckets[i], ensure_ascii=False,
                           separators=(',', ':'))
            )
        if PAGES_JSON.exists():
            PAGES_JSON.unlink()
        print(f'\nwrote {args.shards} shards to {SHARDS_DIR.relative_to(ROOT)}/')
        print(f'removed {PAGES_JSON.relative_to(ROOT)}')
    else:
        print('\n(dry-run; pass --apply to write)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
