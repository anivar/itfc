#!/usr/bin/env python3
"""Restore PDFs we mangled by over-compression from source mirrors.

Compares each PDF in public/ against source copies in
/home/niyam/itfc/recovered{,_alt}/itforchange.net/ and the subdomain
mirrors. If the source is non-trivial (>= 500 KB) and the public/
copy is tiny (< 100 KB), copies the source over.

Tiny PDFs are usually corrupt outputs from compressing already-
truncated source captures.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'public'
SOURCES = [
    Path.home() / 'itfc' / 'recovered' / 'itforchange.net',
    Path.home() / 'itfc' / 'recovered_alt' / 'itforchange.net',
    Path.home() / 'itfc' / 'recovery' / 'subdomains' / 'annual-reports' / 'htdocs',
    Path.home() / 'itfc' / 'recovery' / 'subdomains' / 'projects' / 'htdocs',
]
PUBLIC_PREFIX_TO_SOURCE = {
    'annual-reports/': SOURCES[2],
    'projects/': SOURCES[3],
}
TINY_THRESHOLD = 100 * 1024
GOOD_THRESHOLD = 500 * 1024


def find_source(rel: str) -> Path | None:
    for prefix, src in PUBLIC_PREFIX_TO_SOURCE.items():
        if rel.startswith(prefix):
            cand = src / rel[len(prefix):]
            if cand.is_file():
                return cand
            return None
    # Default: main site sources (file path mirrors site path)
    for src in SOURCES[:2]:
        cand = src / rel
        if cand.is_file():
            return cand
    return None


def main() -> int:
    dry = '--apply' not in sys.argv
    n_restored = 0
    n_no_source = 0
    bytes_restored = 0
    for dp, _dns, fns in os.walk(PUBLIC):
        for fn in fns:
            if not fn.lower().endswith('.pdf'):
                continue
            fp = Path(dp) / fn
            try:
                sz = fp.stat().st_size
            except OSError:
                continue
            if sz >= TINY_THRESHOLD:
                continue
            rel = str(fp.relative_to(PUBLIC)).replace(os.sep, '/')
            src = find_source(rel)
            if src is None or src.stat().st_size < GOOD_THRESHOLD:
                n_no_source += 1
                continue
            print(f'  {sz/1024:5.1f} KB -> {src.stat().st_size/1024/1024:.1f} MB  {rel}')
            if not dry:
                shutil.copy2(src, fp)
            n_restored += 1
            bytes_restored += src.stat().st_size - sz
    verb = 'WOULD restore' if dry else 'restored'
    print(f'\n{verb} {n_restored} PDFs ({bytes_restored/1024/1024:.1f} MB recovered)')
    print(f'tiny but no usable source: {n_no_source}')
    if dry:
        print('\n(dry-run; pass --apply to actually restore)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
