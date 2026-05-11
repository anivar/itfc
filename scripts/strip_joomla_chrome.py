#!/usr/bin/env python3
"""Strip legacy Joomla chrome (nav, sidebars, footer) from body_html.

The Drupal-era Wayback captures of /events/N, /component/content/*, and
other legacy URLs included the FULL Joomla 1.5 page inside body_html —
mainlevel-nav menus, topnav, footer modules, sidebar etc. — wrapping the
actual article. That chrome is now duplicated by Astro's site navigation
and produces a cluttered render.

This script keeps only the article body: every <table class="contentpaneopen">
block AFTER the first one (the first is always the title). If there is
only one contentpaneopen block, we keep the inner content stripping any
contentheading/contentpagetitle row.

Idempotent: rerunning on cleaned content is a no-op.

    python3 scripts/strip_joomla_chrome.py [--apply]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

SHARDS = 'src/data/pages/*.json'

# Match a single <table class="contentpaneopen">...</table> block.
# `.contentpaneopen` tables never nest in Joomla 1.5 — they are always
# top-level siblings — so a non-greedy match is safe.
TABLE_RE = re.compile(
    r'<table[^>]*\bclass="[^"]*\bcontentpaneopen\b[^"]*"[^>]*>.*?</table>',
    re.IGNORECASE | re.DOTALL,
)

# Rows inside the title table — used to drop the heading when there is
# only one contentpaneopen block.
TITLE_ROW_RE = re.compile(
    r'<tr[^>]*>\s*<td[^>]*\bclass="[^"]*\bcontentheading\b[^"]*"[^>]*>.*?</td>\s*</tr>',
    re.IGNORECASE | re.DOTALL,
)


def clean(body: str) -> str | None:
    """Return cleaned body, or None if no change."""
    if 'mainlevel-nav' not in body or 'contentpagetitle' not in body:
        return None

    blocks = TABLE_RE.findall(body)
    if not blocks:
        return None

    # Keep content blocks (skip the title block).
    if len(blocks) >= 2:
        cleaned = ''.join(blocks[1:])
    else:
        # Single contentpaneopen — drop the title row, keep the rest.
        cleaned = TITLE_ROW_RE.sub('', blocks[0])

    cleaned = cleaned.strip()
    if not cleaned or cleaned == body.strip():
        return None
    return cleaned


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    total = 0
    by_shard: dict[str, int] = {}
    bytes_before = 0
    bytes_after = 0
    samples: list[str] = []

    for shard in sorted(glob.glob(SHARDS)):
        with open(shard, 'r', encoding='utf-8') as f:
            pages = json.load(f)
        n = 0
        for p in pages:
            body = p.get('body_html') or ''
            new_body = clean(body)
            if new_body is None:
                continue
            bytes_before += len(body)
            bytes_after += len(new_body)
            p['body_html'] = new_body
            n += 1
            total += 1
            if len(samples) < 8:
                samples.append(
                    f'  {os.path.basename(shard)}  {p.get("slug","?"):60s}  {len(body):>6d} -> {len(new_body):>6d}'
                )
        if n and args.apply:
            with open(shard, 'w', encoding='utf-8') as f:
                json.dump(pages, f, ensure_ascii=False)
        if n:
            by_shard[shard] = n

    pct = (1 - bytes_after / bytes_before) * 100 if bytes_before else 0
    print(f'pages stripped: {total}')
    for s, n in by_shard.items():
        print(f'  {os.path.basename(s)}: {n}')
    print(f'\nbytes: {bytes_before:>9d} -> {bytes_after:>9d}  (-{pct:.1f}%)')
    print('samples:')
    for s in samples:
        print(s)
    if not args.apply:
        print('\n(dry run; pass --apply to write)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
