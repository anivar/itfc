#!/usr/bin/env python3
"""Compress oversized PDFs in public/ via ghostscript (in place).

Walks public/ for PDFs larger than MIN_BYTES, runs ghostscript with
-dPDFSETTINGS=/ebook (150 dpi, modest text/image compression). Keeps
the original if the compressed version is larger than 95% of the
original (no real win).

Pass --apply to write changes; default is dry-run summary.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / 'public'
MIN_BYTES = 3 * 1024 * 1024  # only touch PDFs > 3 MB

GS_ARGS = [
    'gs', '-q', '-dNOPAUSE', '-dBATCH', '-dSAFER',
    '-sDEVICE=pdfwrite',
    '-dCompatibilityLevel=1.5',
    '-dPDFSETTINGS=/ebook',  # ~150 dpi; /screen=72dpi /ebook=150 /printer=300
    '-dDetectDuplicateImages=true',
    '-dColorImageDownsampleType=/Bicubic',
    '-dGrayImageDownsampleType=/Bicubic',
    '-dMonoImageDownsampleType=/Subsample',
]


def compress(path: Path) -> tuple[bool, int, int]:
    before = path.stat().st_size
    tmp = path.with_suffix('.pdf.__tmp')
    try:
        r = subprocess.run(
            GS_ARGS + [f'-sOutputFile={tmp}', str(path)],
            capture_output=True, timeout=120,
        )
        if r.returncode != 0 or not tmp.exists():
            tmp.unlink(missing_ok=True)
            return (False, before, before)
        after = tmp.stat().st_size
        # Don't bother if savings <5%
        if after >= before * 0.95:
            tmp.unlink(missing_ok=True)
            return (False, before, before)
        shutil.move(str(tmp), str(path))
        return (True, before, after)
    except Exception as e:
        print(f'  fail {path}: {e}', file=sys.stderr)
        tmp.unlink(missing_ok=True)
        return (False, before, before)


def main() -> int:
    dry = '--apply' not in sys.argv
    candidates: list[Path] = []
    for dp, _dns, fns in os.walk(SCAN):
        for fn in fns:
            if not fn.lower().endswith('.pdf'):
                continue
            fp = Path(dp) / fn
            try:
                sz = fp.stat().st_size
            except OSError:
                continue
            if sz >= MIN_BYTES:
                candidates.append(fp)
    candidates.sort(key=lambda p: -p.stat().st_size)
    print(f'candidates: {len(candidates)} PDFs > {MIN_BYTES/1024/1024:.0f} MB')
    if dry:
        for fp in candidates[:20]:
            sz = fp.stat().st_size
            print(f'  {sz/1024/1024:6.1f} MB  {fp.relative_to(SCAN)}')
        if len(candidates) > 20:
            print(f'  ... and {len(candidates)-20} more')
        total = sum(p.stat().st_size for p in candidates)
        print(f'total candidate size: {total/1024/1024:.1f} MB')
        print('\n(dry-run; pass --apply to actually compress)')
        return 0
    n_done = 0
    bytes_before = bytes_after = 0
    for fp in candidates:
        ok, b, a = compress(fp)
        if ok:
            n_done += 1
            bytes_before += b
            bytes_after += a
            print(f'  {b/1024/1024:6.1f} -> {a/1024/1024:5.1f} MB  {fp.relative_to(SCAN)}')
    saved = bytes_before - bytes_after
    print(f'\ncompressed {n_done}/{len(candidates)} files; saved {saved/1024/1024:.1f} MB')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
