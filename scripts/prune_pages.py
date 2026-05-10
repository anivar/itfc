#!/usr/bin/env python3
"""Drop classified-irrelevant pages from pages.json.

Reads scripts/_classified.json (run classify_pages.py first). For each
bucket, applies a per-bucket policy:

  junk_slug         drop ALL — already filtered at render time
  template_only     drop ALL — orphaned Joomla scaffolds
  duplicate_body    drop orphans (no inbound links from other pages);
                    keep the ones that are referenced
  duplicate_slug    drop orphans (case-only variants)
  near_empty        drop orphans
  drupal_admin      drop /filter/tips; keep /search and /user/login
                    (they have many inbound links — handled via the
                    redirect step below, not here)
  taxonomy_stub     KEEP — referenced from articles' tags
  mediawiki_special KEEP — referenced inside MediaWiki mirror
  ok                KEEP

Idempotent. Pass --apply to write.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_JSON = ROOT / 'src' / 'data' / 'pages.json'
CLASSIFIED = Path(__file__).resolve().parent / '_classified.json'

DROP_ALL_BUCKETS = {'junk_slug', 'template_only'}
DROP_ORPHAN_BUCKETS = {'duplicate_body', 'duplicate_slug', 'near_empty'}
KEEP_BUCKETS = {'ok', 'taxonomy_stub', 'mediawiki_special'}
SPECIAL_DROP_SLUGS = {'filter/tips'}


def inbound_counts(pages: list[dict], targets: set[str]) -> dict[str, int]:
    counts = {s: 0 for s in targets}
    if not targets:
        return counts
    rx = {s: re.compile(rf'href="/?{re.escape(s)}(?:["#?])') for s in targets}
    for p in pages:
        body = p.get('body_html') or ''
        for s, r in rx.items():
            if r.search(body):
                counts[s] += 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    pages = json.loads(PAGES_JSON.read_text())
    classified = json.loads(CLASSIFIED.read_text())

    drop: set[str] = set()
    drop.update(s for s, b in classified.items() if b in DROP_ALL_BUCKETS)
    drop.update(SPECIAL_DROP_SLUGS & {p['slug'] for p in pages})

    orphan_candidates = {
        s for s, b in classified.items() if b in DROP_ORPHAN_BUCKETS
    }
    inbound = inbound_counts(pages, orphan_candidates)
    drop.update(s for s in orphan_candidates if inbound[s] == 0)

    # Per-bucket dropped breakdown for the report
    by_bucket: Counter[str] = Counter()
    for s in drop:
        by_bucket[classified.get(s, 'unknown')] += 1

    before = len(pages)
    kept = [p for p in pages if p['slug'] not in drop]
    after = len(kept)

    bytes_before = PAGES_JSON.stat().st_size
    print(f'pages: {before}  ->  {after}  (dropped {before - after})')
    print('per-bucket drops:')
    for b, n in by_bucket.most_common():
        print(f'  {b:18s} {n}')

    if args.apply:
        PAGES_JSON.write_text(
            json.dumps(kept, ensure_ascii=False, separators=(',', ':'))
        )
        bytes_after = PAGES_JSON.stat().st_size
        print(f'\nsize: {bytes_before/1024/1024:.1f} MB -> {bytes_after/1024/1024:.1f} MB')
    else:
        print('\n(dry-run; pass --apply to write)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
