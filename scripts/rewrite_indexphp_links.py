#!/usr/bin/env python3
"""Rewrite legacy /index.php/X hrefs to /X in page body HTML.

Wayback captured many internal links in the legacy MediaWiki/Joomla URL
form `<a href="/index.php/PageName">`. The target pages exist in our
corpus under bare slugs (PageName, page-name, etc.) — only the prefix is
legacy. Strip `/index.php/` from any internal href whose remainder
resolves to a known slug or an existing redirect.

Skip wiki-archive pages whose OWN slug contains /index.php/ (e.g.
ITfC_Annual_Report_2013-14/index.php/Main_Page) — those are reproductions
of a wiki snapshot and their internal cross-links should keep the wiki
URL shape so the archived structure stays self-consistent.

Idempotent. Pass --apply to write.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARDS = str(ROOT / 'src/data/pages/*.json')
REDIRECTS_FILE = ROOT / 'src/data/redirects.json'

# href value (group 1 is the path after /index.php/, group 2 is any
# trailing query/hash to preserve).
HREF_RE = re.compile(
    r'''(href=["'])/?index\.php/([^"'#?]*)([#?][^"']*)?(["'])''',
    re.IGNORECASE,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    # Build the resolution set: any slug that exists, or any redirect source.
    slugs: set[str] = set()
    for shard in sorted(glob.glob(SHARDS)):
        with open(shard) as f:
            for p in json.load(f):
                slugs.add(p.get('slug', ''))
    redirects = json.loads(REDIRECTS_FILE.read_text()) if REDIRECTS_FILE.exists() else {}
    red_keys = set(redirects.keys())

    def resolves(target: str) -> bool:
        # Strip query/hash already removed by regex; URL-decode for slug match.
        try:
            t = urllib.parse.unquote(target)
        except Exception:
            t = target
        return t in slugs or ('/' + t) in red_keys

    total_pages = 0
    rewritten_pages = 0
    rewritten_hrefs = 0
    unresolved_hrefs = 0
    unresolved_samples: list[str] = []
    by_shard: dict[str, int] = {}

    for shard in sorted(glob.glob(SHARDS)):
        with open(shard) as f:
            pages = json.load(f)
        changed = False
        n_shard_rewrites = 0
        for p in pages:
            total_pages += 1
            slug = p.get('slug', '') or ''
            # Skip wiki-archive pages reproducing a snapshot's internal links.
            if '/index.php/' in slug:
                continue
            body = p.get('body_html', '') or ''
            if 'index.php/' not in body:
                continue
            page_rewrites = 0

            def repl(m: re.Match) -> str:
                nonlocal page_rewrites
                nonlocal rewritten_hrefs
                nonlocal unresolved_hrefs
                pre, path, tail, post = m.group(1), m.group(2), m.group(3) or '', m.group(4)
                if not resolves(path):
                    unresolved_hrefs += 1
                    if len(unresolved_samples) < 12:
                        unresolved_samples.append(path)
                    return m.group(0)  # leave as-is
                page_rewrites += 1
                rewritten_hrefs += 1
                return f'{pre}/{path}{tail}{post}'

            new_body = HREF_RE.sub(repl, body)
            if new_body != body:
                p['body_html'] = new_body
                rewritten_pages += 1
                n_shard_rewrites += page_rewrites
                changed = True
        if changed:
            by_shard[shard] = n_shard_rewrites
            if args.apply:
                with open(shard, 'w', encoding='utf-8') as f:
                    json.dump(pages, f, ensure_ascii=False)

    print(f'total pages scanned: {total_pages}')
    print(f'pages rewritten:     {rewritten_pages}')
    print(f'hrefs rewritten:     {rewritten_hrefs}')
    print(f'hrefs unresolved (left as-is): {unresolved_hrefs}')
    print()
    print('per-shard rewrite counts:')
    for s, n in by_shard.items():
        print(f'  {Path(s).name}: {n}')
    print()
    print('unresolved sample targets:')
    for t in unresolved_samples:
        print(f'  /index.php/{t}')
    if not args.apply:
        print('\n(dry run; pass --apply to write)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
