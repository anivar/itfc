#!/usr/bin/env python3
"""Turn <a> anchors whose href resolves nowhere into plain spans.

Walks body HTML across all shards; for each `<a href="/X">text</a>`, checks
whether `/X` would actually serve content (a routed Astro page, an existing
redirect, or a real file under public/). If not, replaces the anchor with
`<span class="dead-link">text</span>` so the reader still sees the original
prose without a 404 trap.

External links (http://, https://, mailto:, tel:, //...), in-page anchors
(#foo), and asset-path links (/sites/, /themes/, /_astro/, /files/,
/brand/, /favicon, /api/, /modules/, /core/, /system/) are left alone.

Idempotent. Pass --apply to write.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARDS = str(ROOT / 'src/data/pages/*.json')
REDIRECTS_FILE = ROOT / 'src/data/redirects.json'
PUBLIC = ROOT / 'public'
DIST = ROOT / 'dist'

ASSET_PREFIXES = (
    '/sites/', '/themes/', '/_astro/', '/files/', '/brand/', '/favicon',
    '/api/', '/modules/', '/core/', '/system/', '/profiles/',
)

# An <a> tag with an href attribute. Group 1 = before-href attrs, 2 = quote,
# 3 = href value, 4 = quote, 5 = after-href attrs, 6 = inner HTML.
A_RE = re.compile(
    r'<a\b([^>]*?)\bhref=(["\'])([^"\']*)\2([^>]*)>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


def load_routed() -> set[str]:
    """Slugs routed by the static build, derived from dist/<slug>/index.html
    and dist/<slug>.html. Strip trailing slash; everything is compared
    URL-decoded against the slug form."""
    routed: set[str] = set()
    if not DIST.exists():
        print('WARN: dist/ missing — run `bun run build` first for accurate audit',
              file=sys.stderr)
        return routed
    for p in DIST.rglob('index.html'):
        rel = p.relative_to(DIST).parent.as_posix()
        if rel != '.':
            routed.add(rel)
    for p in DIST.glob('**/*.html'):
        rel = p.relative_to(DIST).as_posix()
        if rel.endswith('/index.html'):
            continue
        if rel.endswith('.html'):
            routed.add(rel[:-5])
    return routed


def load_public_paths() -> set[str]:
    """Static asset paths shipped via public/ (subdomain mirrors,
    images, etc.). A href to /mavc/wp-content/uploads/X.pdf works iff the
    file is present at public/mavc/wp-content/uploads/X.pdf."""
    paths: set[str] = set()
    if not PUBLIC.exists():
        return paths
    for p in PUBLIC.rglob('*'):
        if p.is_file():
            paths.add(p.relative_to(PUBLIC).as_posix())
    return paths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    routed = load_routed()
    public_paths = load_public_paths()
    redirects = json.loads(REDIRECTS_FILE.read_text()) if REDIRECTS_FILE.exists() else {}
    red_keys = set(redirects.keys())
    print(f'routed slugs: {len(routed)}; public assets: {len(public_paths)}; '
          f'redirects: {len(red_keys)}')

    def resolves(href: str) -> bool:
        # Strip query/hash before testing the path.
        path = re.split(r'[#?]', href, 1)[0]
        if not path or path == '/':
            return True
        # Trailing-slash normalisation; Astro is trailingSlash:'ignore'.
        path_no_slash = path.rstrip('/')
        if path_no_slash in red_keys or path in red_keys:
            return True
        if not path.startswith('/'):
            return True  # let relative/anchor links pass; A_RE pre-filters externals
        tail = path[1:]
        tail_no_slash = path_no_slash[1:]
        try:
            tail_dec = urllib.parse.unquote(tail)
            tail_dec_no = urllib.parse.unquote(tail_no_slash)
        except Exception:
            tail_dec = tail
            tail_dec_no = tail_no_slash
        if tail_no_slash in routed or tail_dec_no in routed:
            return True
        if tail in public_paths or tail_dec in public_paths:
            return True
        # Some folders ship as a public/ directory only; test for any
        # file inside that directory (e.g. /mavc/ as a folder index).
        if any(p.startswith(tail_no_slash + '/') or p.startswith(tail_dec_no + '/')
               for p in public_paths):
            return True
        return False

    total_anchors = 0
    dead_anchors = 0
    pages_touched = 0
    sample_dead: list[tuple[str, str]] = []
    by_shard: dict[str, int] = {}

    for shard in sorted(glob.glob(SHARDS)):
        with open(shard) as f:
            pages = json.load(f)
        n_shard = 0
        shard_changed = False
        for p in pages:
            body = p.get('body_html', '') or ''
            if not body or '<a' not in body:
                continue
            page_dead = 0

            def repl(m: re.Match) -> str:
                nonlocal page_dead
                nonlocal sample_dead
                nonlocal total_anchors
                pre, _q, href, post, inner = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
                total_anchors += 1
                # Untouched: externals, mailto, tel, in-page, javascript, data.
                if href.startswith(('http://', 'https://', '//', 'mailto:',
                                    'tel:', '#', 'javascript:', 'data:')):
                    return m.group(0)
                if href.startswith(ASSET_PREFIXES):
                    return m.group(0)
                if not href.startswith('/'):
                    return m.group(0)
                if resolves(href):
                    return m.group(0)
                page_dead += 1
                if len(sample_dead) < 10:
                    sample_dead.append((href, inner[:60]))
                return f'<span class="dead-link" title="archived link no longer resolves">{inner}</span>'

            new_body = A_RE.sub(repl, body)
            if new_body != body:
                p['body_html'] = new_body
                pages_touched += 1
                n_shard += page_dead
                dead_anchors += page_dead
                shard_changed = True
        if shard_changed:
            by_shard[shard] = n_shard
            if args.apply:
                with open(shard, 'w', encoding='utf-8') as f:
                    json.dump(pages, f, ensure_ascii=False)

    print(f'total <a> tags scanned: {total_anchors}')
    print(f'dead anchors neutralized: {dead_anchors}')
    print(f'pages touched: {pages_touched}')
    print()
    print('per-shard counts:')
    for s, n in by_shard.items():
        print(f'  {Path(s).name}: {n}')
    print()
    print('sample dead hrefs:')
    for href, txt in sample_dead:
        print(f'  {href}   ({txt!r})')
    if not args.apply:
        print('\n(dry run; pass --apply to write)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
