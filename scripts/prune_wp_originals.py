#!/usr/bin/env python3
"""Drop oversized WordPress original images that have resampled variants.

WordPress uploads include the source image plus generated variants like
`name-1024x768.png`, `name-2048x1536.png`. HTML pages reference the
variants for display, so the originals are usually only used for
"view full size" links — fine to drop when they're huge.

Walks public/ for image files >MIN_BYTES that DON'T have a
`-WIDTHxHEIGHT` suffix and whose directory contains at least one
sibling with the same stem and that suffix shape. Removes them.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / 'public'
MIN_BYTES = 4 * 1024 * 1024  # 4 MB threshold; smaller originals stay

VARIANT_RE = re.compile(r'-(\d+)x(\d+)$')
IMG_EXT = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}


def is_variant(stem: str) -> bool:
    return bool(VARIANT_RE.search(stem))


def main() -> int:
    n_removed = 0
    bytes_removed = 0
    for dp, _dns, fns in os.walk(SCAN):
        # Group siblings by base stem (the stem with -NxN stripped)
        siblings: dict[tuple[str, str], list[str]] = {}
        for fn in fns:
            p = Path(fn)
            if p.suffix.lower() not in IMG_EXT:
                continue
            stem = p.stem
            base = VARIANT_RE.sub('', stem)
            siblings.setdefault((base, p.suffix.lower()), []).append(fn)

        for (base, ext), files in siblings.items():
            originals = [f for f in files if not is_variant(Path(f).stem)]
            variants = [f for f in files if is_variant(Path(f).stem)]
            if not variants:
                continue
            for orig in originals:
                fp = Path(dp) / orig
                try:
                    sz = fp.stat().st_size
                except OSError:
                    continue
                if sz < MIN_BYTES:
                    continue
                try:
                    fp.unlink()
                except OSError as e:
                    print(f'  fail rm {fp}: {e}', file=sys.stderr)
                    continue
                n_removed += 1
                bytes_removed += sz
    print(f'pruned {n_removed} originals, freed {bytes_removed/1024/1024:.1f} MB')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
