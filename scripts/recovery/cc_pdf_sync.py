#!/usr/bin/env python3
"""
Fill missing PDFs from a local Common Crawl backup. Match by URL-decoded
path since CC stores files with literal characters (spaces, ampersands)
while our missing list has URL-encoded refs.

Env vars:
  CC_ROOT       — root of the Common Crawl mirror (required)
  PUBLIC        — Astro public/ dir (default: ./public)
  WAYBACK_PUBS  — working dir holding missing-pdfs.json (default: data/wayback-pubs)
"""
import os, json, urllib.parse, shutil, glob

CC_ROOT = os.environ['CC_ROOT']
PUBLIC = os.environ.get('PUBLIC', 'public')
LIST = os.path.join(os.environ.get('WAYBACK_PUBS', 'data/wayback-pubs'), 'missing-pdfs.json')

# Build CC index: decoded relative path → absolute file path
cc_index = {}
for root, _, files in os.walk(CC_ROOT):
    for fn in files:
        if not fn.lower().endswith('.pdf'): continue
        full = os.path.join(root, fn)
        rel = '/' + os.path.relpath(full, CC_ROOT)
        cc_index[rel] = full

print(f'CC PDF index: {len(cc_index)} files')

miss = json.load(open(LIST))
print(f'Missing in public/: {len(miss)}')

copied = []
already = []
no_match = []
for ref in miss:
    target = f'{PUBLIC}{ref}'
    if os.path.exists(target) and os.path.getsize(target) > 100:
        already.append(ref); continue
    decoded = urllib.parse.unquote(ref)
    src = cc_index.get(decoded) or cc_index.get(ref)
    if not src:
        no_match.append(ref); continue
    # ext4 limits filenames to 255 bytes — URL-encoded multi-byte glyphs
    # explode past that. Skip the path so existing body_html links 404
    # instead of erroring the whole sync.
    if len(os.path.basename(target).encode('utf-8')) > 255:
        no_match.append(ref); continue
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(src, target)
    copied.append(ref)

print(f'\nAlready in public/: {len(already)}')
print(f'Copied from CC backup: {len(copied)}')
print(f'No CC match: {len(no_match)}')
print()
print('First 10 copied:')
for r in copied[:10]: print(f'  {r}')
print('\nFirst 10 still-missing:')
for r in no_match[:10]: print(f'  {r}')
