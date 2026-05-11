# Archive ingest toolkit

Utilities for building and refreshing the site's content from public web
archives (Common Crawl and the Internet Archive's Wayback Machine).

For day-to-day maintenance use `scripts/refetch_latest.py`. Reach for
these only for bulk operations:

- Mirror a host from Wayback at scale.
- Rebuild the publications catalogue.
- Reconcile PDFs against a Common Crawl dump.

All scripts use the Python 3.10+ standard library, **except** the two
pacers (`pacer_subdomain.py`, `wb_h2_pacer.py`) which depend on
`httpx[http2]`. Those declare the dependency inline via a PEP 723
metadata block and are run with [uv](https://docs.astral.sh/uv/):

```sh
uv run scripts/recovery/wb_h2_pacer.py     # uv resolves httpx on the fly
```

If you prefer not to install uv, install `httpx[http2]` in a venv
manually and invoke with `python3` instead.

## Scripts

| Script | Purpose |
|---|---|
| `pacer_subdomain.py` | AIMD-paced Wayback fetcher restricted to one host. Reads TSV (timestamp, mime, url) on stdin, saves bodies under `$OUT_ROOT`. |
| `wb_h2_pacer.py` | Same idea, host-agnostic — pace any Wayback URL list over one HTTP/2 connection. |
| `cc_index.py` | Bulk CDX query of every Common Crawl monthly index for `itforchange.net/*`. Writes a JSONL manifest with WARC location info. |
| `cc_fetch.py` | Fetch one Common Crawl WARC record (given a JSONL line from the manifest) via a Range request to `data.commoncrawl.org`. |
| `cdx_pdfs.py` | Discover every PDF Wayback has captured for the domain, in one CDX call. |
| `cc_pdf_sync.py` | Resolve missing PDFs against a local Common Crawl mirror by URL-decoded path matching. |
| `fetch_pdfs_v2.py` | Paced PDF fetcher driven by CDX-discovered `(path, timestamp)` pairs. Resumable. |
| `cdx_all_papers.py` | CDX prefix query for paper-shaped slugs across four time windows. |
| `extract_pub_urls.py` | Parse archived listing pages into a structured catalogue. |
| `build_master_catalog.py` | Reconcile CDX timestamps + listing catalogue + corpus shards into `src/data/publications.json`. |
| `cleanup_redirect_collisions.py` | Drop redirects whose source path collides with a real file in `public/`. |

## Environment variables

| Var | Default | Used by |
|---|---|---|
| `OUT_ROOT` | `recovered/itforchange.net` | pacers, cc_fetch |
| `LOG_DIR` | `logs/` | pacers, cc_fetch, cc_index |
| `DATA_DIR` | `data/` | cc_index |
| `WAYBACK_PUBS` | `data/wayback-pubs/` | publications scripts |
| `CC_ROOT` | _(required)_ | cc_pdf_sync |
| `PUBLIC` | `public/` | cc_pdf_sync, fetch_pdfs_v2 |
| `HOST` | _(required)_ | pacer_subdomain |
| `RATE_INITIAL` | `0.5` | pacers |
| `CONCURRENCY` | `6` | pacers |

## Common Crawl ingest

```sh
# 1. Walk monthly CC indexes and build the manifest
python3 scripts/recovery/cc_index.py --indexes 24
# → data/cc_captures.jsonl (~12 MB, ~15,000 records)

# 2. Range-fetch each WARC record in parallel
cat data/cc_captures.jsonl \
  | xargs -d '\n' -P 4 -I{} python3 scripts/recovery/cc_fetch.py '{}'
# → recovered_alt/itforchange.net/<path>
```

`cc_fetch.py` issues an HTTP **Range** request for the exact byte range
of each capture's WARC record — the standard CC access pattern. Four
parallel workers is a safe default.

A pre-built manifest is checked in at `manifests/cc_captures.jsonl` so
the ingest can be reproduced without re-running step 1.

## Wayback ingest

Wayback has no bulk WARC API. Discover URLs via CDX, then pull each one
through the raw-bytes envelope `https://web.archive.org/web/<TS>id_/<URL>`:

```sh
# 1. Discover URLs (one CDX call)
curl -s 'https://web.archive.org/cdx/search/cdx?url=itforchange.net/&matchType=prefix&filter=statuscode:200&fl=timestamp,mime,original&collapse=urlkey&output=json' \
  > data/wayback-pubs/cdx-all.json

# 2. Convert to TSV and feed the pacer
python3 -c "
import json
rows = json.load(open('data/wayback-pubs/cdx-all.json'))[1:]
for ts, mime, url in rows:
    print(f'{ts}\t{mime}\t{url}')
" | OUT_ROOT=recovered/itforchange.net LOG_DIR=logs \
    python3 scripts/recovery/wb_h2_pacer.py
```

The pacer opens **one** HTTP/2 connection and multiplexes up to 6
requests on it. Starting rate 0.5 req/s; after every 50 successes it
adds 0.1 req/s; on any 429 or 5xx it halves the rate. Same AIMD control
law as TCP — Wayback throttles on TCP-connection establishment rate, not
request rate, so a single multiplexed connection sustains 55–65 req/min
indefinitely while a naive multi-connection fetcher trips throttles
within minutes.

## Subdomains

Different host, same pacer, scoped via `HOST`:

```sh
HOST=projects.itforchange.net \
LOG_PREFIX=projects \
OUT_ROOT=public/projects \
LOG_DIR=logs/pacer \
python3 scripts/recovery/pacer_subdomain.py < projects.tsv
```

## Publications rebuild

```sh
python3 scripts/recovery/cdx_all_papers.py        # paper slugs
python3 scripts/recovery/cdx_pdfs.py              # PDF inventory
python3 scripts/recovery/extract_pub_urls.py      # parse listing pages
python3 scripts/recovery/build_master_catalog.py  # → src/data/publications.json
```

## Notes

- `recovered/`, `recovered_alt/`, `logs/`, `data/wayback-pubs/` are all
  gitignored. They hold large working data and should not be committed.
- The publications data shipped at `src/data/publications.json` is the
  build-time input — these scripts produce it, but you don't need to
  re-run them unless reconciling new captures.
