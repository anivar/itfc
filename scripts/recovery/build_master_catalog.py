#!/usr/bin/env python3
"""
Combine sources to produce the master /resources_all catalog:

- CDX-discovered slugs (1224) provide the canonical paper list + a
  timestamp we use as freshness ranking.
- Listing-derived catalog (99) overlays better titles + summaries +
  listing-page-position for the most recent ~99 papers.
- Corpus entries (pages.json) provide titles + body_html → summaries
  for the rest.
- 6 brand-new papers from listings (no individual snapshot) get added
  to the corpus as metadata-only entries.

Output:
  src/data/publications.json — master ordered list:
    [{slug, title, summary_html, image, year}, …]

Env vars:
  WAYBACK_PUBS — dir holding cdx-all.json + catalog.json (default: data/wayback-pubs)
"""
import json, glob, re, html as ihtml, os, urllib.parse

PAGES_DIR = 'src/data/pages'
OUT = 'src/data/publications.json'
_WP = os.environ.get('WAYBACK_PUBS', 'data/wayback-pubs')

# Load corpus
corpus = {}
shard_for_slug = {}
for f in sorted(glob.glob(f'{PAGES_DIR}/*.json')):
    shard_id = int(re.search(r'(\d+)\.json', f).group(1))
    arr = json.load(open(f))
    for p in arr:
        slug = (p.get('slug') or '').lstrip('/')
        if slug:
            corpus[slug] = p
            shard_for_slug[slug] = shard_id
        for a in (p.get('aliases') or []):
            a = a.lstrip('/').replace('index.php/', '', 1)
            if a and a not in corpus:
                corpus[a] = p

cdx = json.load(open(f'{_WP}/cdx-all.json'))   # slug -> latest ts
listing_cat = json.load(open(f'{_WP}/catalog.json'))  # listing-derived
listing_by_slug = {e['slug']: e for e in listing_cat}

# Decoded variant for matching
def alt(slug):
    return urllib.parse.unquote(slug)

# Build master catalog list
master = []
for slug, ts in cdx.items():
    if slug == 'sitemap': continue
    p = corpus.get(slug) or corpus.get(alt(slug))
    listing = listing_by_slug.get(slug)

    title = (listing or {}).get('title') or (p or {}).get('title') or slug.replace('-', ' ').title()
    summary_html = (listing or {}).get('summary_html', '').strip()
    image = (listing or {}).get('image')

    # Fallback summary from corpus body_html: first <p>
    if not summary_html and p:
        body = p.get('body_html', '') or ''
        # Strip front matter image-fields if any
        m = re.search(r'<p[^>]*>(.*?)</p>', body, re.DOTALL)
        if m:
            txt = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if len(txt) > 30:
                summary_html = txt[:280] + ('…' if len(txt) > 280 else '')

    # Year from CDX timestamp
    year = ts[:4]

    master.append({
        'slug': slug,
        'title': ihtml.unescape(title.strip()),
        'summary_html': summary_html,
        'image': image,
        'year': year,
        'ts': ts,
    })

# Now overlay the 6 brand-new papers (in listing_cat but not in CDX)
for slug, e in listing_by_slug.items():
    if slug in cdx: continue
    master.append({
        'slug': slug,
        'title': ihtml.unescape(e['title'].strip()),
        'summary_html': e.get('summary_html', '').strip(),
        'image': e.get('image'),
        'year': '2026',  # they appeared in April 2026 listings
        'ts': '20260424201529',
    })

# Sort: newest first by ts desc
master.sort(key=lambda x: x['ts'], reverse=True)

# Drop ts from final output (used only for sort)
for x in master:
    del x['ts']

with open(OUT, 'w') as f:
    json.dump(master, f, ensure_ascii=False, indent=0,
              separators=(',', ':'))

print(f'master catalog: {len(master)} papers')
print(f'  with summary: {sum(1 for x in master if x["summary_html"])}')
print(f'  with image:   {sum(1 for x in master if x["image"])}')
print(f'  by year:')
from collections import Counter
for y, n in sorted(Counter(x["year"] for x in master).items(), reverse=True):
    print(f'    {y}: {n}')

print(f'\nfirst 5:')
for x in master[:5]:
    print(f'  [{x["year"]}] {x["title"][:70]}')

print(f'\nlast 5:')
for x in master[-5:]:
    print(f'  [{x["year"]}] {x["title"][:70]}')
