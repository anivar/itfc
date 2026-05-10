#!/usr/bin/env python3
"""Patch MediaWiki annual-report mirrors to fix entry-point and skin gaps.

For each archived MediaWiki dir under public/ that has a
`index.php/Main_Page/index.html`:
  - write `<dir>/index.html` redirecting to `index.php/Main_Page/`
  - write `<dir>/index.php/index.html` redirecting to `Main_Page/`

Also fans out the only captured `skins/common/` tree (in
public/annual-reports/Annual_Report_2013-14/) into siblings that
reference `skins/common/...` but don't have it.

Idempotent. Pass --apply to write; default is dry-run.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'public'
PAGES_JSON = ROOT / 'src' / 'data' / 'pages.json'

REDIRECT_HTML = """<!doctype html>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0; url={target}">
<link rel="canonical" href="{target}">
<title>Redirecting…</title>
<p>Redirecting to <a href="{target}">{target}</a>.</p>
"""


def find_wiki_roots() -> list[Path]:
    """Wiki roots = directories that need entry redirects.

    Two sources:
      1. Existing public/ dirs with `index.php/Main_Page/index.html`.
      2. pages.json slugs ending `/index.php/Main_Page` (those become
         dist/<root>/index.php/Main_Page/index.html at build time).
    """
    roots: set[Path] = set()
    for dp, dns, _fns in os.walk(PUBLIC):
        if 'index.php' in dns:
            mp = Path(dp) / 'index.php' / 'Main_Page' / 'index.html'
            if mp.is_file():
                roots.add(Path(dp))
    try:
        pages = json.loads(PAGES_JSON.read_text())
    except (OSError, json.JSONDecodeError):
        pages = []
    for p in pages:
        slug = p.get('slug', '')
        if slug.endswith('/index.php/Main_Page'):
            root_rel = slug[: -len('/index.php/Main_Page')]
            roots.add(PUBLIC / root_rel)
    return sorted(roots)


def find_skins_donor() -> Path | None:
    cand = PUBLIC / 'annual-reports' / 'Annual_Report_2013-14' / 'skins' / 'common'
    return cand if cand.is_dir() else None


def main() -> int:
    apply = '--apply' in sys.argv
    actions: list[str] = []

    for root in find_wiki_roots():
        rel = root.relative_to(PUBLIC)
        # 1) <root>/index.html -> index.php/Main_Page/
        idx = root / 'index.html'
        if not idx.exists():
            actions.append(f'WRITE {rel}/index.html')
            if apply:
                idx.parent.mkdir(parents=True, exist_ok=True)
                idx.write_text(REDIRECT_HTML.format(target='index.php/Main_Page/'))
        # 2) <root>/index.php/index.html -> Main_Page/
        idx2 = root / 'index.php' / 'index.html'
        if not idx2.exists():
            actions.append(f'WRITE {rel}/index.php/index.html')
            if apply:
                idx2.parent.mkdir(parents=True, exist_ok=True)
                idx2.write_text(REDIRECT_HTML.format(target='Main_Page/'))

    donor = find_skins_donor()
    if donor:
        for root in find_wiki_roots():
            target = root / 'skins' / 'common'
            if target.exists():
                continue
            rel = root.relative_to(PUBLIC)
            actions.append(f'COPY skins/common -> {rel}/skins/common')
            if apply:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(donor, target)

    print(f'wiki roots found: {len(find_wiki_roots())}')
    print(f'donor skins/common: {donor}')
    print(f'actions: {len(actions)}')
    for a in actions[:40]:
        print(f'  {a}')
    if len(actions) > 40:
        print(f'  ... and {len(actions)-40} more')
    if not apply:
        print('\n(dry-run; pass --apply to actually patch)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
