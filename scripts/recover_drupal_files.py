#!/usr/bin/env python3
"""Recover missing /sites/default/files/* PDFs from source mirrors.

Reads scripts/_gaps.json, finds entries under sites/default/files/ that
also exist (by exact same relative path) in the source mirrors at
/home/niyam/itfc/recovered{,_alt}/itforchange.net/, and copies the
highest-impact ones (most referrers per byte) into public/ until the
size budget is exhausted.

After running, re-run compress_pdfs.py to /ebook-shrink the new files
before commit.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'public'
GAPS_JSON = Path(__file__).resolve().parent / '_gaps.json'

SOURCE_MIRRORS = [
    Path.home() / 'itfc' / 'recovered' / 'itforchange.net',
    Path.home() / 'itfc' / 'recovered_alt' / 'itforchange.net',
]
PREFIX = 'sites/default/files/'
MIN_FILE_BYTES = 20 * 1024  # exclude wayback 404 stubs / partials


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--budget-mb', type=int, default=100,
                    help='cap total restore size (MB)')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    g = json.loads(GAPS_JSON.read_text())
    broken = {t: refs for t, refs in g['broken'].items() if t.startswith(PREFIX)}

    mirror_index: dict[str, Path] = {}
    for m in SOURCE_MIRRORS:
        if not m.exists():
            continue
        for p in m.rglob(f'{PREFIX}**/*.pdf'):
            if p.is_file():
                mirror_index.setdefault(str(p.relative_to(m)), p)

    candidates: list[tuple[str, int, int, Path]] = []
    for t, refs in broken.items():
        src = mirror_index.get(t)
        if src is None:
            continue
        size = src.stat().st_size
        if size < MIN_FILE_BYTES:
            continue
        candidates.append((t, len(refs), size, src))

    # Highest impact first: most refs, then smallest size.
    candidates.sort(key=lambda x: (-x[1], x[2]))

    budget = args.budget_mb * 1024 * 1024
    chosen: list[tuple[str, int, int, Path]] = []
    total = 0
    for c in candidates:
        if total + c[2] > budget:
            continue
        chosen.append(c)
        total += c[2]

    print(f'available: {len(candidates)} files (total {sum(c[2] for c in candidates)/1024/1024:.0f} MB)')
    print(f'within {args.budget_mb} MB budget: {len(chosen)} files = {total/1024/1024:.1f} MB')
    print(f'broken refs that would resolve: {sum(c[1] for c in chosen)}')
    print()

    n_done = 0
    for t, n_refs, size, src in chosen:
        dst = PUBLIC / t
        if dst.exists():
            continue
        print(f'  {n_refs:3d} refs / {size/1024:5.0f} KB  {t}')
        if args.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        n_done += 1

    verb = 'restored' if args.apply else 'WOULD restore'
    print(f'\n{verb} {n_done} PDFs')
    if not args.apply:
        print('(dry-run; pass --apply to copy)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
