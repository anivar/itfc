#!/usr/bin/env python3
"""
CDX query for all itforchange.net snapshots in the late-2024 → 2026
window (when the slug-based publication URLs existed). Filter to
slug-shaped paths: lowercase-hyphenated, no /sites/, no /index.php?, no
/node/N, no taxonomy/, no static asset extensions.
"""
import urllib.request, ssl, json, re, os, time
ctx = ssl.create_default_context()
UA = 'Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0'

WINDOWS = [
    ('20231001', '20240601'),
    ('20240601', '20250101'),
    ('20250101', '20250601'),
    ('20250601', '20260601'),
]
_WP = os.environ.get('WAYBACK_PUBS', 'data/wayback-pubs')
os.makedirs(_WP, exist_ok=True)
OUT = os.path.join(_WP, 'cdx-all.json')

# What we strip out
SKIP_PATH_RX = re.compile(
    r'^(?:'
    r'sites/|themes/|modules/|core/|user/|admin/|node/\d+|taxonomy/|comment/'
    r'|search/|user|admin|cron\.php|update\.php|install\.php|robots\.txt'
    r'|index\.php(?:\?|/?$)'
    r'|index\.php/(?:taxonomy|search|user|admin)'
    r')',
    re.IGNORECASE,
)
ASSET_EXT_RX = re.compile(r'\.(?:css|js|jpe?g|png|gif|svg|ico|woff2?|ttf|pdf|mp[34]|webp|json|xml|txt)(?:\?|$)', re.IGNORECASE)
SLUG_RX = re.compile(r'^[a-z0-9][-a-z0-9_%]+$', re.IGNORECASE)  # at least 2 chars

def fetch(url, timeout=180):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()

def is_paper_url(orig):
    # strip scheme + host
    m = re.match(r'^https?://itforchange\.net/(.*)$', orig, re.IGNORECASE)
    if not m: return False
    path = m.group(1).split('?', 1)[0].split('#', 1)[0].rstrip('/')
    # strip /index.php/ prefix
    path = re.sub(r'^index\.php/', '', path, flags=re.IGNORECASE)
    if not path: return False
    if SKIP_PATH_RX.match(path): return False
    if ASSET_EXT_RX.search(path): return False
    # only single-segment slugs (papers are flat slugs in Drupal URL aliases)
    if '/' in path: return False
    if not SLUG_RX.match(path): return False
    if len(path) < 4: return False
    return True

discovered = {}  # slug -> latest_ts
seen_rows = 0
for from_ts, to_ts in WINDOWS:
    url = ('https://web.archive.org/cdx/search/cdx?'
           'url=itforchange.net/&matchType=prefix&'
           f'from={from_ts}&to={to_ts}&'
           'filter=statuscode:200&filter=mimetype:text/html&'
           'output=json&fl=timestamp,original&limit=20000&'
           'collapse=urlkey')
    print(f'CDX {from_ts}-{to_ts} ...', flush=True)
    for attempt in range(3):
        try:
            data = fetch(url)
            rows = json.loads(data)
            print(f'  {len(rows)} rows', flush=True)
            for row in rows[1:]:
                seen_rows += 1
                ts, orig = row[0], row[1]
                if not is_paper_url(orig): continue
                slug = re.sub(r'^https?://itforchange\.net/(?:index\.php/)?', '', orig, flags=re.IGNORECASE)
                slug = slug.split('?', 1)[0].split('#', 1)[0].rstrip('/')
                if slug not in discovered or ts > discovered[slug]:
                    discovered[slug] = ts
            break
        except Exception as e:
            wait = [30, 90, 180][attempt]
            print(f'  retry in {wait}s ({e})', flush=True)
            time.sleep(wait)
    time.sleep(8)

print(f'\nseen rows: {seen_rows}')
print(f'unique paper-shaped slugs: {len(discovered)}')

with open(OUT, 'w') as f:
    json.dump(discovered, f, indent=2)
print(f'saved {OUT}')
