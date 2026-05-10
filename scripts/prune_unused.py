#!/usr/bin/env python3
"""Delete files in public/ not referenced by any HTML.

Walk every .html in public/ and the body_html of every page in
src/data/pages.json, collect every same-origin URL they reference
(img/link/script/iframe/source/anchor + url(...) inside style attrs),
normalize to filesystem paths under public/, then delete every file
in public/ not in that set.

Always-kept regardless of references:
  - brand/, favicon.*, robots.txt, *.xml at root, .well-known/
  - themes/  (Drupal theme assets shared across many pages)
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'public'
PAGES_JSON = ROOT / 'src' / 'data' / 'pages.json'
BASE = '/itfc/'  # current deploy base; rewriter strips this when matching

# Pull every same-origin URL out of an HTML/CSS/etc. blob.
URL_PATTERNS = [
    re.compile(r'(?i)\b(?:src|href|action|poster|data-src)\s*=\s*"([^"#?]+)(?:[?#][^"]*)?"'),
    re.compile(r"(?i)\b(?:src|href|action|poster|data-src)\s*=\s*'([^'#?]+)(?:[?#][^']*)?'"),
    re.compile(r'(?i)srcset\s*=\s*"([^"]+)"'),
    re.compile(r"(?i)srcset\s*=\s*'([^']+)'"),
    re.compile(r'(?i)url\(\s*["\']?([^"\')\s#?]+)(?:[?#][^"\')]*)?["\']?\s*\)'),
]

# Folders preserved unconditionally
KEEP_PREFIXES = (
    'brand/', 'themes/', '.well-known/',
)
KEEP_FILES = {
    'favicon.ico', 'favicon.svg', 'robots.txt', 'CNAME', '.nojekyll',
}


def split_srcset(val: str) -> list[str]:
    out = []
    for chunk in val.split(','):
        url = chunk.strip().split(maxsplit=1)[0]
        if url:
            out.append(url)
    return out


def extract_urls(blob: str) -> set[str]:
    found: set[str] = set()
    for rx in URL_PATTERNS:
        for m in rx.finditer(blob):
            v = m.group(1)
            if 'srcset' in rx.pattern.lower():
                for u in split_srcset(v):
                    found.add(u)
            else:
                found.add(v)
    return found


def normalize(url: str) -> str | None:
    """Return repo-relative path under public/, or None if not local."""
    if not url:
        return None
    url = url.strip()
    # External or scheme-prefixed
    if url.startswith(('http://', 'https://', '//', 'mailto:', 'tel:', 'data:', '#', 'javascript:')):
        return None
    url = urllib.parse.unquote(url.split('#', 1)[0].split('?', 1)[0])
    if not url:
        return None
    # Strip BASE prefix if present
    if url.startswith(BASE):
        url = url[len(BASE):]
    elif url.startswith('/'):
        url = url.lstrip('/')
    else:
        # Relative path — can't resolve without dirname context; skip
        return None
    return url


def is_keep_unconditionally(rel: str) -> bool:
    if rel in KEEP_FILES:
        return True
    return any(rel.startswith(p) for p in KEEP_PREFIXES)


def scan_html_file(path: Path) -> set[str]:
    try:
        return extract_urls(path.read_text(encoding='utf-8', errors='replace'))
    except Exception:
        return set()


def scan_relative(path: Path, urls: set[str]) -> set[str]:
    """Resolve relative URLs against a host HTML file's directory."""
    out: set[str] = set()
    parent = path.parent.relative_to(PUBLIC)
    for u in urls:
        if u.startswith(('http://', 'https://', '//', 'mailto:', 'tel:', 'data:', '#', 'javascript:')):
            continue
        if u.startswith('/') or u.startswith(BASE):
            continue
        clean = urllib.parse.unquote(u.split('#', 1)[0].split('?', 1)[0])
        if not clean:
            continue
        try:
            resolved = (parent / clean).resolve().relative_to(PUBLIC.resolve())
            out.add(str(resolved).replace(os.sep, '/'))
        except (ValueError, OSError):
            continue
    return out


def main() -> int:
    referenced: set[str] = set()

    # 1. Scan all HTML files under public/
    n_html = 0
    for dp, _dns, fns in os.walk(PUBLIC):
        for fn in fns:
            if not fn.lower().endswith(('.html', '.htm', '.css')):
                continue
            n_html += 1
            fp = Path(dp) / fn
            urls = scan_html_file(fp)
            # Absolute (root or BASE-prefixed)
            for u in urls:
                rel = normalize(u)
                if rel:
                    referenced.add(rel)
            # Relative — resolve against parent dir
            referenced |= scan_relative(fp, urls)

    # 2. Scan body_html in pages.json
    try:
        pages = json.loads(PAGES_JSON.read_text())
    except Exception:
        pages = []
    for p in pages:
        body = p.get('body_html') or ''
        for u in extract_urls(body):
            rel = normalize(u)
            if rel:
                referenced.add(rel)

    print(f'scanned {n_html} html/css files in public/, {len(pages)} pages.json entries')
    print(f'unique referenced paths: {len(referenced)}')

    # 3. Walk public/ and decide what to keep
    dry = '--apply' not in sys.argv
    n_kept_html = n_kept_ref = n_kept_force = 0
    n_removed = 0
    bytes_removed = 0
    by_topdir: dict[str, tuple[int, int]] = {}  # topdir -> (count, bytes)
    for dp, _dns, fns in os.walk(PUBLIC):
        for fn in fns:
            fp = Path(dp) / fn
            rel = str(fp.relative_to(PUBLIC)).replace(os.sep, '/')
            if fn.lower().endswith(('.html', '.htm', '.css')):
                n_kept_html += 1
                continue
            if is_keep_unconditionally(rel):
                n_kept_force += 1
                continue
            if rel in referenced:
                n_kept_ref += 1
                continue
            try:
                sz = fp.stat().st_size
            except OSError:
                continue
            bytes_removed += sz
            n_removed += 1
            top = rel.split('/', 1)[0]
            c, b = by_topdir.get(top, (0, 0))
            by_topdir[top] = (c + 1, b + sz)
            if not dry:
                try:
                    fp.unlink()
                except OSError as e:
                    print(f'  fail rm {fp}: {e}', file=sys.stderr)

    if not dry:
        # 4. Remove now-empty directories (bottom-up)
        for dp, _dns, _fns in os.walk(PUBLIC, topdown=False):
            if dp == str(PUBLIC):
                continue
            try:
                os.rmdir(dp)
            except OSError:
                pass  # not empty

    print(f'kept html/css: {n_kept_html}')
    print(f'kept (referenced): {n_kept_ref}')
    print(f'kept (always): {n_kept_force}')
    verb = 'WOULD remove' if dry else 'removed'
    print(f'{verb}: {n_removed} files, would free {bytes_removed/1024/1024:.1f} MB')
    print('\nby top-level dir:')
    for top, (c, b) in sorted(by_topdir.items(), key=lambda x: -x[1][1]):
        print(f'  {top:30s}  {c:6d} files  {b/1024/1024:8.1f} MB')
    if dry:
        print('\n(dry-run; pass --apply to actually delete)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
