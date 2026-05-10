#!/usr/bin/env python3
"""Add legacy `*.html` → canonical-slug redirects to redirects.json.

For every broken `<slug>.html` reference recorded in scripts/_gaps.json,
emit a 302 to `/<slug>` when `<slug>` exists in pages.json (as a slug or
alias canonical). Idempotent — existing entries are kept untouched.

Pass --apply to write; default is dry-run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_JSON = ROOT / 'src' / 'data' / 'pages.json'
REDIRECTS_JSON = ROOT / 'src' / 'data' / 'redirects.json'
GAPS_JSON = Path(__file__).resolve().parent / '_gaps.json'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    pages = json.loads(PAGES_JSON.read_text())
    by_slug = {p['slug'] for p in pages}
    aliases: dict[str, str] = {}
    for p in pages:
        for a in p.get('aliases') or []:
            aliases[a.lstrip('/')] = p['slug']

    gaps = json.loads(GAPS_JSON.read_text())
    redirects = json.loads(REDIRECTS_JSON.read_text())

    added = 0
    skipped_existing = 0
    no_dest = 0
    examples: list[str] = []

    for target in gaps['broken']:
        if not target.endswith('.html') or target.startswith('index.php/'):
            continue
        # Skip subdomain dirs — those are real files in public/, not slugs
        if target.startswith(('annual-reports/', 'projects/')):
            continue
        bare = target[:-5]
        dest_slug = bare if bare in by_slug else aliases.get(bare)
        if not dest_slug:
            no_dest += 1
            continue
        from_path = f'/{target}'
        if from_path in redirects:
            skipped_existing += 1
            continue
        redirects[from_path] = f'/{dest_slug}'
        added += 1
        if len(examples) < 10:
            examples.append(f'  {from_path}  ->  /{dest_slug}')

    print(f'broken .html refs (apex-only):  {sum(1 for t in gaps["broken"] if t.endswith(".html") and not t.startswith("index.php/") and not t.startswith(("annual-reports/","projects/")))}')
    print(f'  matched to a slug/alias:      {added + skipped_existing}')
    print(f'  already in redirects.json:    {skipped_existing}')
    print(f'  newly added:                  {added}')
    print(f'  no slug/alias match:          {no_dest}')
    if examples:
        print('\nexamples:')
        for e in examples:
            print(e)

    if args.apply and added:
        # Sort for stable diffs
        sorted_map = dict(sorted(redirects.items()))
        REDIRECTS_JSON.write_text(
            json.dumps(sorted_map, ensure_ascii=False, indent=0) + '\n'
        )
        print(f'\nwrote {REDIRECTS_JSON} ({len(sorted_map)} total redirects)')
    elif not args.apply:
        print('\n(dry-run; pass --apply to write)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
