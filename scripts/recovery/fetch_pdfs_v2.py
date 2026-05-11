#!/usr/bin/env python3
"""
Fetch PDFs using CDX-discovered (path, ts) pairs. Much faster than v1
because we skip availability lookups — the CDX query already proved the
snapshot exists.

Saves to ./public/<path>. Resumable (skips existing files).

Env vars:
  PUBLIC        — Astro public/ dir (default: ./public)
  WAYBACK_PUBS  — working dir for pdfs-fetchable.json + pdfs-v2-log.json
                  (default: data/wayback-pubs)
"""
import urllib.request, ssl, json, os, time
ctx = ssl.create_default_context()

PUBLIC = os.environ.get('PUBLIC', 'public')
_WP = os.environ.get('WAYBACK_PUBS', 'data/wayback-pubs')
LIST = os.path.join(_WP, 'pdfs-fetchable.json')  # [(ref, ts, orig), …]
LOG = os.path.join(_WP, 'pdfs-v2-log.json')
THROTTLE = 3
RETRY_BACKOFF = [10, 30, 60]
UA = 'Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0'

def fetch(url, timeout=120):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()

def main():
    items = json.load(open(LIST))
    log = json.load(open(LOG)) if os.path.exists(LOG) else {'ok': {}, 'fail': []}

    total = len(items)
    ok = skipped = 0
    fail = []

    for i, (ref, ts, orig) in enumerate(items, 1):
        target = f'{PUBLIC}{ref}'
        if os.path.exists(target) and os.path.getsize(target) > 100:
            skipped += 1; ok += 1; continue

        url = f'https://web.archive.org/web/{ts}id_/{orig}'
        success = False
        last_err = None
        for attempt in range(len(RETRY_BACKOFF) + 1):
            try:
                data = fetch(url)
                if len(data) < 100:
                    last_err = f'tiny ({len(data)}B)'
                    break
                if not (data[:4] == b'%PDF' or b'%PDF' in data[:1024]):
                    last_err = f'not-pdf ({len(data)}B)'
                    break
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, 'wb') as f: f.write(data)
                ok += 1; success = True
                log['ok'][ref] = ts
                if i % 10 == 0 or i < 5:
                    print(f'  [{i}/{total}] GOT {ref[:80]} ({len(data)} B)', flush=True)
                break
            except Exception as e:
                last_err = str(e)
                if '404' in last_err:
                    break
                if attempt < len(RETRY_BACKOFF):
                    time.sleep(RETRY_BACKOFF[attempt])
        if not success:
            fail.append((ref, last_err))
            print(f'  [{i}/{total}] FAIL {ref[:60]}  ({last_err})', flush=True)
            log['fail'].append([ref, last_err])

        if i % 25 == 0:
            with open(LOG, 'w') as f: json.dump(log, f, indent=2)
            print(f'  --- progress: ok={ok}/{i}  fail={len(fail)}  remaining={total-i}', flush=True)

        if success:
            time.sleep(THROTTLE)

    with open(LOG, 'w') as f: json.dump(log, f, indent=2)
    print(f'\nDone. ok={ok}/{total}  skipped(cached)={skipped}  failed={len(fail)}')


if __name__ == '__main__':
    main()
