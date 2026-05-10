#!/usr/bin/env python3
"""Find broken same-origin references across the built site.

Walks every .html in dist/, extracts every href/src/srcset/action/poster
plus url(...) inside style attrs, normalizes to a path under dist/, and
reports references that don't resolve to an existing file (or directory
with index.html).

Output: top broken targets by reference count, plus a per-page sample
of referrers, written to scripts/_gaps.json + summary on stdout.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
BASE = '/itfc/'  # build base; rewriter strips this when matching

URL_PATTERNS = [
    re.compile(r'(?i)\b(?:src|href|action|poster|data-src)\s*=\s*"([^"#]+?)"'),
    re.compile(r"(?i)\b(?:src|href|action|poster|data-src)\s*=\s*'([^'#]+?)'"),
    re.compile(r'(?i)srcset\s*=\s*"([^"]+)"'),
    re.compile(r"(?i)srcset\s*=\s*'([^']+)'"),
    re.compile(r'(?i)url\(\s*["\']?([^"\')\s]+?)["\']?\s*\)'),
]


def split_srcset(val: str) -> list[str]:
    out = []
    for chunk in val.split(','):
        url = chunk.strip().split(maxsplit=1)[0]
        if url:
            out.append(url)
    return out


def extract(blob: str) -> set[str]:
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


SKIP_SCHEMES = ('http://', 'https://', '//', 'mailto:', 'tel:', 'data:', '#', 'javascript:', 'ftp:', 'irc:')


def resolve(url: str, host_dir: Path) -> Path | None:
    if not url or url.startswith(SKIP_SCHEMES):
        return None
    url = url.split('#', 1)[0].split('?', 1)[0]
    if not url:
        return None
    url = urllib.parse.unquote(url)
    if url.startswith(BASE):
        url = url[len(BASE):]
        target = DIST / url
    elif url.startswith('/'):
        url = url.lstrip('/')
        target = DIST / url
    else:
        target = host_dir / url
    try:
        target = target.resolve()
        target.relative_to(DIST.resolve())
    except (ValueError, OSError):
        return None
    return target


def exists_as_page(target: Path) -> bool:
    if target.is_file():
        return True
    if target.is_dir() and (target / 'index.html').is_file():
        return True
    # No-extension URL that wasn't a dir? Astro emits foo/index.html for /foo
    if not target.suffix:
        sib = target.with_suffix('.html')
        if sib.is_file():
            return True
    return False


def main() -> int:
    broken: dict[str, list[str]] = defaultdict(list)  # target -> [referrers]
    n_html = 0
    n_refs = 0
    n_broken = 0

    for dp, _dns, fns in os.walk(DIST):
        for fn in fns:
            if not fn.lower().endswith('.html'):
                continue
            n_html += 1
            fp = Path(dp) / fn
            try:
                blob = fp.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            urls = extract(blob)
            for u in urls:
                target = resolve(u, fp.parent)
                if target is None:
                    continue
                n_refs += 1
                if not exists_as_page(target):
                    rel_target = str(target.relative_to(DIST.resolve())).replace(os.sep, '/')
                    rel_referrer = str(fp.relative_to(DIST)).replace(os.sep, '/')
                    broken[rel_target].append(rel_referrer)
                    n_broken += 1

    print(f'scanned {n_html} html files, {n_refs} same-origin refs, {n_broken} broken')
    print(f'unique broken targets: {len(broken)}')

    # group by top-level dir
    by_top: dict[str, int] = defaultdict(int)
    for t, refs in broken.items():
        top = t.split('/', 1)[0]
        by_top[top] += len(refs)
    print('\nbroken refs by top-level dir:')
    for top, n in sorted(by_top.items(), key=lambda x: -x[1])[:20]:
        print(f'  {n:6d}  {top}')

    # top broken targets
    print('\ntop 30 broken targets by ref count:')
    for t, refs in sorted(broken.items(), key=lambda x: -len(x[1]))[:30]:
        print(f'  {len(refs):5d}  {t}')

    out = {
        'summary': {
            'html_scanned': n_html,
            'refs_total': n_refs,
            'refs_broken': n_broken,
            'unique_broken_targets': len(broken),
        },
        'by_top': dict(sorted(by_top.items(), key=lambda x: -x[1])),
        'broken': {t: sorted(set(refs))[:20] for t, refs in broken.items()},
    }
    out_path = Path(__file__).resolve().parent / '_gaps.json'
    out_path.write_text(json.dumps(out, indent=2))
    print(f'\nwrote {out_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
