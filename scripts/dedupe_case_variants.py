#!/usr/bin/env python3
"""Collapse casing-only duplicate slug pairs.

A handful of Wayback-captured slugs differ only in letter case
(e.g. /team vs /Team, /joinus vs /Joinus, /volunteer/Anita vs
/volunteer/anita). The earlier dedupe pass keyed on body-hash and
missed these because internal hrefs differ slightly between the
variants (each self-references its own capitalisation), so the
bytes don't match exactly.

Policy: lowercase wins (matches Drupal's clean-URL convention and
the more common inbound link form). Before dropping the
non-canonical variant, compare the latest year mentioned in each
body — if the uppercase variant references a strictly newer year
than the lowercase one, flag it so a human can decide rather than
silently discarding the newer capture.

Pass --apply to write.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARDS = sorted(glob.glob(str(ROOT / 'src/data/pages/*.json')))
REDIRECTS_FILE = ROOT / 'src/data/redirects.json'

YEAR_RE = re.compile(r'\b(20[0-3][0-9])\b')


def latest_year(html: str) -> int:
    years = [int(y) for y in YEAR_RE.findall(html or '')]
    return max(years) if years else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    # slug -> (shard_path, page_dict, page_index)
    locate: dict[str, tuple[str, dict, int]] = {}
    shard_pages: dict[str, list[dict]] = {}
    for shard in SHARDS:
        pages = json.load(open(shard))
        shard_pages[shard] = pages
        for i, p in enumerate(pages):
            locate[p['slug']] = (shard, p, i)

    groups: dict[str, list[str]] = defaultdict(list)
    for slug in locate:
        groups[slug.lower()].append(slug)
    dupes = {k: v for k, v in groups.items() if len(v) > 1}

    redirects = json.loads(REDIRECTS_FILE.read_text()) if REDIRECTS_FILE.exists() else {}

    flagged: list[str] = []
    plan: list[tuple[str, str, str, str]] = []  # canonical, drop, canon_year, drop_year

    for lc, variants in sorted(dupes.items()):
        # Canonical-pick policy:
        #   1. variant with the strictly newest year mentioned in body
        #      (catches stale lowercase captures like /rti vs /RTI)
        #   2. tie-break by longer body (more content = likely later
        #      capture)
        #   3. final tie-break: lowercase wins (Drupal clean-URL
        #      convention; matches most inbound links)
        def score(slug: str) -> tuple:
            body = locate[slug][1].get('body_html', '') or ''
            return (
                latest_year(body),
                # tiebreak: prefer all-lowercase (Drupal clean-URL form)
                # — negative count so max() picks the lowercase variant.
                -sum(1 for c in slug if c.isupper()),
            )
        canonical = max(variants, key=score)
        drops = [v for v in variants if v != canonical]

        canon_body = locate[canonical][1].get('body_html', '') or ''
        canon_year = latest_year(canon_body)
        for drop in drops:
            drop_body = locate[drop][1].get('body_html', '') or ''
            drop_year = latest_year(drop_body)
            plan.append((canonical, drop, canon_year, drop_year))
            # Sanity flag: the policy should never pick a canonical
            # with an older year than a drop. If it does, something's
            # wrong with the score function.
            if drop_year > canon_year:
                flagged.append(
                    f'  BUG: /{drop} has newer year {drop_year} vs '
                    f'canonical /{canonical} {canon_year}'
                )

    print(f'casing-only duplicate groups: {len(dupes)}')
    print(f'planned drops: {len(plan)}')
    print()
    print('plan (canonical <- drop  [latest-year:canon/drop]):')
    for canonical, drop, cy, dy in plan:
        mark = ' *' if dy > cy else ''
        print(f'  /{canonical:55s} <- /{drop:55s}  [{cy}/{dy}]{mark}')

    if flagged:
        print()
        print('flagged for human review (newer content in drop candidate):')
        for line in flagged:
            print(line)

    if not args.apply:
        print('\n(dry run; pass --apply to write)')
        return 0

    # Apply: drop non-canonical pages from their shards, add redirects.
    drops_by_shard: dict[str, set[str]] = defaultdict(set)
    for canonical, drop, _, _ in plan:
        shard, _, _ = locate[drop]
        drops_by_shard[shard].add(drop)
        redirects[f'/{drop}'] = f'/{canonical}'

    for shard, drop_slugs in drops_by_shard.items():
        before = len(shard_pages[shard])
        shard_pages[shard] = [p for p in shard_pages[shard] if p['slug'] not in drop_slugs]
        after = len(shard_pages[shard])
        print(f'  {Path(shard).name}: {before} -> {after}')
        with open(shard, 'w', encoding='utf-8') as f:
            json.dump(shard_pages[shard], f, ensure_ascii=False)

    with open(REDIRECTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(redirects, f, ensure_ascii=False, indent=2)
    print(f'redirects total: {len(redirects)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
