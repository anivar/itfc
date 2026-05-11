#!/usr/bin/env python3
"""
Extract publication URLs and metadata from each fetched listing page.
Builds $WAYBACK_PUBS/catalog.json with: slug, title, image src, summary,
date, listing_page, row_html. Strips wayback prefix forms.

Env vars:
  WAYBACK_PUBS — working dir (default: data/wayback-pubs)
"""
import os, re, json, glob, urllib.parse

OUT = os.environ.get('WAYBACK_PUBS', 'data/wayback-pubs')

def clean_wayback(html):
    html = re.sub(r'https://web\.archive\.org/web/\d+\w*/', '', html)
    html = re.sub(r'/web/\d+\w*/(?:https?://itforchange\.net)?', '', html)
    return html

def extract_rows(html):
    out = []
    pat = re.compile(r'<div class="views-row">')
    i = 0
    while True:
        m = pat.search(html, i)
        if not m: break
        body_start = html.find('>', m.end()-1) + 1
        depth = 1; j = body_start; found = False
        for tk in re.finditer(r'<(/?)div\b[^>]*>', html[body_start:]):
            if tk.group(1): depth -= 1
            else: depth += 1
            if depth == 0:
                j = body_start + tk.end(); found = True; break
        if not found: break
        out.append(html[m.start():j])
        i = j
    return out

def first(rx, s, group=1, default=None):
    m = re.search(rx, s, re.DOTALL)
    return m.group(group).strip() if m else default

catalog = []
for f in sorted(glob.glob(f'{OUT}/page-*.html'), key=lambda p: int(re.search(r'page-(\d+)', p).group(1))):
    page_num = int(re.search(r'page-(\d+)', f).group(1))
    html = clean_wayback(open(f).read())
    rows = extract_rows(html)
    for row in rows:
        m = re.search(r'<h3[^>]*class="field-content"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', row)
        if not m: continue
        href, title = m.group(1), m.group(2).strip()
        href = href.replace('/index.php/', '/', 1) if href.startswith('/index.php/') else href
        slug = href.lstrip('/').rstrip('/')
        # Skip non-publication links (asset paths, anchors)
        if not slug or '#' in slug: continue
        img = first(r'<img[^>]*src="([^"]+)"', row)
        if img:
            img = img.split('?',1)[0]  # drop query
        body_html = first(r'<div class="views-field views-field-body[^"]*"[^>]*><div class="field-content">(.*?)</div></div>', row, default='')
        date = first(r'<span[^>]*class="[^"]*date[^"]*"[^>]*>([^<]+)</span>', row, default='')
        catalog.append({
            'slug': slug,
            'title': title,
            'image': img,
            'summary_html': body_html,
            'date_str': date,
            'listing_page': page_num,
        })

# Dedupe by slug, keep first occurrence (which is from earliest page = newest)
seen = set(); deduped = []
for entry in catalog:
    if entry['slug'] in seen: continue
    seen.add(entry['slug']); deduped.append(entry)

with open(f'{OUT}/catalog.json', 'w') as f:
    json.dump(deduped, f, ensure_ascii=False, indent=2)

print(f'pages scanned: {len(glob.glob(f"{OUT}/page-*.html"))}')
print(f'rows: {len(catalog)}, unique: {len(deduped)}')
print('\nfirst 5:')
for e in deduped[:5]:
    print(f'  {e["slug"]}  ({e["title"][:60]})')
