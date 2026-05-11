#!/usr/bin/env python3
"""
Use CDX API to discover ALL itforchange.net PDF snapshots in one shot.
Output: $WAYBACK_PUBS/cdx-pdfs.json mapping path → (timestamp, original_url).

Much faster than per-URL availability checks: one API call returns
thousands of rows.
"""
import os, urllib.request, ssl, json, re, time
from pathlib import Path
ctx = ssl.create_default_context()
UA = 'Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0'
WAYBACK_PUBS = Path(os.environ.get('WAYBACK_PUBS', 'data/wayback-pubs'))
WAYBACK_PUBS.mkdir(parents=True, exist_ok=True)
OUT = str(WAYBACK_PUBS / 'cdx-pdfs.json')

def fetch(url, timeout=180):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()

# Two queries: by mime + the older /media/ tree
# CDX with collapse=urlkey returns one row per unique URL, latest by default
QUERIES = [
    'https://web.archive.org/cdx/search/cdx?'
    'url=itforchange.net/&matchType=prefix&'
    'filter=mimetype:application/pdf&filter=statuscode:200&'
    'collapse=urlkey&output=json&fl=timestamp,original&limit=20000',
]

discovered = {}  # path (root-relative, decoded) -> (ts, original_url)
for i, q in enumerate(QUERIES, 1):
    print(f'CDX query {i}/{len(QUERIES)}', flush=True)
    for attempt in range(3):
        try:
            data = fetch(q)
            rows = json.loads(data)
            print(f'  {len(rows)} rows', flush=True)
            for row in rows[1:]:
                ts, orig = row[0], row[1]
                m = re.match(r'^https?://(?:www\.)?itforchange\.net(/.*)$', orig, re.IGNORECASE)
                if not m: continue
                path = m.group(1).split('?', 1)[0]
                # Use latest timestamp per path
                cur = discovered.get(path)
                if cur is None or ts > cur[0]:
                    discovered[path] = (ts, orig)
            break
        except Exception as e:
            wait = [30, 90, 180][attempt]
            print(f'  retry in {wait}s ({e})', flush=True)
            time.sleep(wait)
    time.sleep(8)

print(f'\nDiscovered: {len(discovered)} unique PDF paths in wayback')
json.dump({k: v for k, v in discovered.items()}, open(OUT, 'w'), indent=2)
print(f'saved {OUT}')
