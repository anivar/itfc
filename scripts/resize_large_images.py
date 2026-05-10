#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["Pillow>=10.4"]
# ///
"""Downscale large images in public/ in place.

Walks public/ for {png,jpg,jpeg,webp} files larger than MIN_BYTES.
Resizes any whose longest dimension exceeds MAX_DIM, keeps aspect
ratio, re-encodes JPEG at Q85 / PNG with optimize+compression. Skips
files smaller than the threshold and ones already small-dimensioned.

Pass --apply to write changes; default is dry-run with size summary.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SCAN = ROOT / 'public'
MIN_BYTES = 1 * 1024 * 1024  # only touch files > 1 MB
MAX_DIM = 1600                # cap longest side
JPEG_Q = 85


def process(path: Path, dry: bool) -> tuple[bool, int, int]:
    try:
        before = path.stat().st_size
        with Image.open(path) as im:
            w, h = im.size
            if max(w, h) <= MAX_DIM and before <= MIN_BYTES * 4:
                return (False, before, before)
            im.load()
            ratio = MAX_DIM / max(w, h)
            new = im
            if ratio < 1.0:
                new_w, new_h = int(w * ratio), int(h * ratio)
                new = im.resize((new_w, new_h), Image.LANCZOS)
            ext = path.suffix.lower()
            if dry:
                # Estimate by re-encoding to memory? Cheaper: assume 30% of original.
                est = int(before * 0.3) if ratio < 1 else int(before * 0.6)
                return (True, before, est)
            tmp = path.with_suffix(path.suffix + '.__tmp')
            if ext in ('.jpg', '.jpeg'):
                if new.mode in ('RGBA', 'P'):
                    new = new.convert('RGB')
                new.save(tmp, 'JPEG', quality=JPEG_Q, optimize=True, progressive=True)
            elif ext == '.png':
                new.save(tmp, 'PNG', optimize=True, compress_level=9)
            elif ext == '.webp':
                new.save(tmp, 'WEBP', quality=JPEG_Q, method=6)
            else:
                tmp.unlink(missing_ok=True)
                return (False, before, before)
            after = tmp.stat().st_size
            if after >= before:
                # Encoded version is bigger — keep original
                tmp.unlink(missing_ok=True)
                return (False, before, before)
            tmp.replace(path)
            return (True, before, after)
    except Exception as e:
        print(f'  fail {path}: {e}', file=sys.stderr)
        return (False, 0, 0)


def main() -> int:
    dry = '--apply' not in sys.argv
    n_touched = 0
    bytes_before = bytes_after = 0
    bytes_skipped = 0
    n_skipped = 0
    samples: list[tuple[str, int, int]] = []
    for dp, _dns, fns in os.walk(SCAN):
        for fn in fns:
            ext = fn.lower().rsplit('.', 1)[-1]
            if ext not in ('png', 'jpg', 'jpeg', 'webp'):
                continue
            fp = Path(dp) / fn
            try:
                sz = fp.stat().st_size
            except OSError:
                continue
            if sz < MIN_BYTES:
                n_skipped += 1
                bytes_skipped += sz
                continue
            changed, before, after = process(fp, dry)
            if changed:
                n_touched += 1
                bytes_before += before
                bytes_after += after
                samples.append((str(fp.relative_to(SCAN)), before, after))
    samples.sort(key=lambda x: -(x[1] - x[2]))
    print('top 15 by savings:')
    for rel, b, a in samples[:15]:
        print(f'  {b/1024/1024:6.1f} -> {a/1024/1024:5.1f} MB  {rel}')
    saved = bytes_before - bytes_after
    verb = 'WOULD save' if dry else 'saved'
    print(f'\nresized: {n_touched} files; {verb} {saved/1024/1024:.1f} MB '
          f'({bytes_before/1024/1024:.1f} -> {bytes_after/1024/1024:.1f} MB)')
    if dry:
        print('\n(dry-run; pass --apply to actually rewrite files)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
