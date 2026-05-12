#!/usr/bin/env python3
"""Collapse duplicate-body slug groups into a canonical URL + redirects.

Many pages were captured under multiple slug variants by Wayback (Drupal
node/N + friendly slug, Joomla events/N + events/N-friendly + resapub/N +
ig/77-igf/N-friendly + component/content/article/N-friendly, typo fixes,
case variants, etc.). They all share identical body_html.

For each group:
  1. Pick canonical slug (score: prefer friendly /events/N-name >
     /resapub/N > /ig/77-igf/N > /component/content/article/N; prefer
     fewer slashes; alpha tie-break).
  2. Add redirect entries `<other>` -> `<canonical>` to redirects.json.
  3. Delete the non-canonical pages from the shard JSON.

Idempotent. Pass --apply to write.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARDS = str(ROOT / 'src/data/pages/*.json')
REDIRECTS_FILE = ROOT / 'src/data/redirects.json'

# Body length below which we ignore duplicates (would over-collapse near-empty
# pages that are just the same boilerplate / title shell).
MIN_BODY = 200


def canonical_score(slug: str) -> tuple:
    """Lower = better canonical.

    The live Drupal site's canonical URL for content is the lowercase
    hyphen-separated friendly slug (e.g.
    /digital-india-whose-india-whose-agenda). The wiki/Joomla-era underscore
    forms (`/Digital_India_Whose_India_Whose_agenda`) and `node/N` /
    `events/N` numeric forms exist only as redirect sources. Score them
    worse than the Drupal-friendly form so dedupe picks the right canonical.
    """
    has_space = ' ' in slug
    has_underscore = '_' in slug
    has_upper = any(c.isupper() for c in slug)
    return (
        # Spaces in a URL slug are always wrong — usually a wiki page title
        # that wasn't sanitised. Demote hard.
        1 if has_space else 0,
        # Drupal-friendly slug is lowercase hyphenated; demote any with
        # underscores or uppercase (the wiki/Joomla legacy forms).
        1 if has_underscore else 0,
        1 if has_upper else 0,
        # Friendly slug beats bare numeric: prefer events/52-wsis-ii over events/52
        1 if re.match(r'^events/\d+$', slug) else 0,
        # Same for node/N — almost always there's a friendlier alias
        1 if re.match(r'^node/\d+$', slug) else 0,
        # Top-level Joomla event slug beats deeper variants
        0 if slug.startswith('events/') else
        1 if slug.startswith('resapub/') else
        2 if slug.startswith('ig/') else
        3 if slug.startswith('component/content/') else
        0,  # everything else is fine top-level
        # Prefer no /component/ prefix
        1 if 'component/content' in slug else 0,
        # Prefer fewer slashes
        slug.count('/'),
        len(slug),
        slug,  # tie-break alpha
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    # Group all pages by content hash
    groups: dict[str, list[dict]] = defaultdict(list)
    for shard in sorted(glob.glob(SHARDS)):
        with open(shard, 'r', encoding='utf-8') as f:
            for p in json.load(f):
                body = p.get('body_html', '') or ''
                if len(body) < MIN_BODY:
                    continue
                h = hashlib.sha256(body.encode()).hexdigest()
                groups[h].append({
                    'shard': shard,
                    'slug': p.get('slug', ''),
                    'title': p.get('title', ''),
                    'sz': len(body),
                })

    dupes = {h: g for h, g in groups.items() if len(g) > 1}
    print(f'duplicate-body groups: {len(dupes)} (touching {sum(len(g) for g in dupes.values())} pages)')

    # Load existing redirects
    redirects: dict[str, str] = {}
    if REDIRECTS_FILE.exists():
        redirects = json.loads(REDIRECTS_FILE.read_text())
    print(f'existing redirects: {len(redirects)}')

    new_redirects: dict[str, str] = {}
    drop_slugs: set[str] = set()
    canonical_count = 0

    for h, g in dupes.items():
        g_sorted = sorted(g, key=lambda r: canonical_score(r['slug']))
        canonical = g_sorted[0]
        canon_path = '/' + canonical['slug']
        canonical_count += 1
        for other in g_sorted[1:]:
            other_path = '/' + other['slug']
            # Skip if already redirected somewhere (don't overwrite)
            existing = redirects.get(other_path)
            if existing and existing != canon_path:
                continue
            # Don't redirect to itself or create a cycle
            if other_path == canon_path:
                continue
            new_redirects[other_path] = canon_path
            drop_slugs.add(other['slug'])

    print(f'pages to keep as canonical: {canonical_count}')
    print(f'pages to drop (redirect aliases): {len(drop_slugs)}')
    print(f'new redirect entries: {len(new_redirects)}')

    # Show first 5 examples
    print()
    print('=== first 5 redirect examples ===')
    for k in list(new_redirects.keys())[:5]:
        print(f'  {k}  ->  {new_redirects[k]}')

    if not args.apply:
        print('\n(dry run; pass --apply to write)')
        return 0

    # Write redirects (preserve original 0-indent compact format if used)
    redirects.update(new_redirects)
    sorted_keys = sorted(redirects.keys())
    # Detect existing format: read raw, see if original was 0-indent
    raw = REDIRECTS_FILE.read_text() if REDIRECTS_FILE.exists() else '{}'
    is_compact_0indent = '\n' in raw and raw.startswith('{\n') and not raw.startswith('{\n  ')
    if is_compact_0indent:
        body = '{\n' + ',\n'.join(
            f'{json.dumps(k)}: {json.dumps(redirects[k])}' for k in sorted_keys
        ) + '\n}\n'
        REDIRECTS_FILE.write_text(body)
    else:
        REDIRECTS_FILE.write_text(json.dumps(
            {k: redirects[k] for k in sorted_keys}, indent=2, ensure_ascii=False
        ) + '\n')

    # Drop the non-canonical pages from each shard
    by_shard_dropped: dict[str, int] = {}
    for shard in sorted(glob.glob(SHARDS)):
        with open(shard, 'r', encoding='utf-8') as f:
            pages = json.load(f)
        kept = [p for p in pages if (p.get('slug') or '') not in drop_slugs]
        n = len(pages) - len(kept)
        if n:
            by_shard_dropped[shard] = n
            with open(shard, 'w', encoding='utf-8') as f:
                json.dump(kept, f, ensure_ascii=False)

    print()
    print(f'wrote {len(redirects)} total redirects to {REDIRECTS_FILE.name}')
    print(f'pages removed from shards: {sum(by_shard_dropped.values())}')
    for s, n in by_shard_dropped.items():
        print(f'  {s}: -{n}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
