#!/usr/bin/env python3
"""Delete pages that are already filtered out at render time.

Two categories of dead weight in the corpus that the [...slug].astro router
already excludes from build output but still bloat the JSON shards and any
classification report:

  1. "Fatal Error." captures — Wayback grabbed Joomla's error template
     instead of the real page (engine 500'd at capture time).
     ~30 pages, all under inclusionroundtable2014/.

  2. Empty taxonomy/term/<id> stubs — Drupal generated thousands of
     category index pages; many were captured as title-only HTML with no
     content (often 0 bytes). ~44 pages.

     We deliberately do NOT touch node/<id> stubs even if they are short:
     several are legitimate carousel-slide / feature-card content (e.g.
     node/1722 "COVID-19 RELIEF", node/1989 "Launching DataSyn") whose
     full body lives elsewhere — short body is by design.

Idempotent. Pass --apply to write.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys

SHARDS = 'src/data/pages/*.json'


def is_fatal_error(p: dict) -> bool:
    return (p.get('title') or '').strip().lower().startswith('fatal error')


def word_count(html: str) -> int:
    return len(re.findall(r'\w+', re.sub(r'<[^>]+>', ' ', html or '')))


def is_empty_shell(p: dict) -> bool:
    slug = (p.get('slug') or '')
    if not slug.startswith('taxonomy/term/'):
        return False
    return word_count(p.get('body_html') or '') < 30


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    fatal: list[str] = []
    shells: list[str] = []
    by_shard: dict[str, dict[str, int]] = {}

    for shard in sorted(glob.glob(SHARDS)):
        with open(shard, 'r', encoding='utf-8') as f:
            pages = json.load(f)
        kept = []
        n_fatal = n_shell = 0
        for p in pages:
            if is_fatal_error(p):
                fatal.append(p.get('slug', ''))
                n_fatal += 1
                continue
            if is_empty_shell(p):
                shells.append(p.get('slug', ''))
                n_shell += 1
                continue
            kept.append(p)
        if n_fatal or n_shell:
            by_shard[shard] = {'fatal': n_fatal, 'shell': n_shell}
            if args.apply:
                with open(shard, 'w', encoding='utf-8') as f:
                    json.dump(kept, f, ensure_ascii=False)

    print(f'fatal_error captures dropped: {len(fatal)}')
    print(f'empty taxonomy/node shells dropped: {len(shells)}')
    print(f'total: {len(fatal) + len(shells)}')
    print()
    print('per-shard breakdown:')
    for s, c in by_shard.items():
        print(f'  {s}: -{c["fatal"]} fatal, -{c["shell"]} shells')
    print()
    print('fatal_error samples:')
    for s in fatal[:8]:
        print(f'  {s}')
    print()
    print('empty-shell samples:')
    for s in shells[:8]:
        print(f'  {s}')
    if not args.apply:
        print('\n(dry run; pass --apply to write)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
