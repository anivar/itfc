#!/usr/bin/env python3
"""Mirror annual-reports + projects subdomain trees into public/.

Static HTML microsites are copied verbatim to:
  public/annual-reports/  ← from $AR_SRC
  public/projects/         ← from $PROJ_SRC

Inside HTML files, absolute origins are rewritten so links resolve
under the deploy base. The base path comes from $BASE_PATH (default
"/itfc/" matching the GH Pages showcase). Re-run after the official
domain CNAME flip with BASE_PATH=/.

Skips:
  - files > 25 MB that are not PDFs (the WordPress original PNGs;
    smaller resampled variants live next to them and are kept)
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'public'
BASE = os.environ.get('BASE_PATH', '/itfc/')
if not BASE.endswith('/'):
    BASE += '/'

AR_SRC = Path(os.environ.get('AR_SRC',
              '/home/niyam/itfc/recovery/subdomains/annual-reports/htdocs'))
PROJ_SRC = Path(os.environ.get('PROJ_SRC',
                '/home/niyam/itfc/recovery/subdomains/projects/htdocs'))

MAX_NONPDF = 25 * 1024 * 1024  # 25 MB

# Match absolute origins (with optional www) for the three hosts.
HOST_RE = re.compile(
    r'(?i)https?://(?:www\.)?(annual-reports|projects)\.itforchange\.net'
)
APEX_RE = re.compile(
    r'(?i)https?://(?:www\.)?itforchange\.net'
)


def rewrite_html(text: str) -> str:
    # Subdomain origins → BASE + subdomain/
    text = HOST_RE.sub(lambda m: f'{BASE}{m.group(1).lower()}', text)
    # Apex origins → BASE
    text = APEX_RE.sub(BASE.rstrip('/'), text)
    return text


def copy_tree(src: Path, dst_name: str) -> tuple[int, int, int]:
    if not src.is_dir():
        print(f'skip missing source: {src}', file=sys.stderr)
        return (0, 0, 0)
    dst = PUBLIC / dst_name
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    n_copied = n_skipped = n_rewritten = 0
    for dp, dns, fns in os.walk(src):
        rel = Path(dp).relative_to(src)
        out_dir = dst / rel
        out_dir.mkdir(parents=True, exist_ok=True)
        for fn in fns:
            sp = Path(dp) / fn
            op = out_dir / fn
            try:
                size = sp.stat().st_size
            except OSError:
                continue
            if size > MAX_NONPDF and not fn.lower().endswith('.pdf'):
                n_skipped += 1
                continue
            if fn.lower().endswith(('.html', '.htm')):
                try:
                    text = sp.read_text(encoding='utf-8', errors='replace')
                except Exception:
                    shutil.copy2(sp, op)
                    n_copied += 1
                    continue
                new = rewrite_html(text)
                op.write_text(new, encoding='utf-8')
                n_copied += 1
                if new != text:
                    n_rewritten += 1
            else:
                shutil.copy2(sp, op)
                n_copied += 1
    return (n_copied, n_skipped, n_rewritten)


def main() -> int:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    print(f'BASE_PATH={BASE}')
    for label, src, name in (
        ('annual-reports', AR_SRC, 'annual-reports'),
        ('projects', PROJ_SRC, 'projects'),
    ):
        c, s, r = copy_tree(src, name)
        print(f'{label}: copied={c} skipped_oversize={s} html_rewritten={r}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
