#!/usr/bin/env python3
"""Ingest refreshed HTML files from the wayback recovery tree into the
Astro shards.

Scope:
  - Source tree: ~/itfc/recovered/itforchange.net (HTTP/2 pacer output)
  - Target: src/data/pages/*.json
  - Operation: for each .html file under the source whose mtime is at or
    after --since, derive its slug, find the matching page in any shard,
    and replace body_html (+ title if non-empty) with freshly-extracted
    content. New slugs are inserted into the smallest shard.

Why mtime, not full re-import: the pacer just touched the files we care
about; mtime ≥ --since is a clean filter that ignores stale pages we
deliberately pruned earlier.

Body extraction: reuses the same heuristics as scripts/import_cc_content.py
(div#content / region-content / main / article / body, in priority order).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

# Reuse the proven extractor + URL normalizer from the import script
sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_cc_content import (  # noqa: E402
    extract,
    file_to_url_path,
    primary_slug,
)

ROOT = Path(__file__).resolve().parent.parent
SHARDS_DIR = ROOT / 'src' / 'data' / 'pages'
DEFAULT_SOURCE = Path.home() / 'itfc' / 'recovered' / 'itforchange.net'
LOG = Path(__file__).resolve().parent / '_ingest_refreshed.json'


def load_shards():
    files = sorted(SHARDS_DIR.glob('*.json'))
    by_slug: dict[str, tuple[Path, dict]] = {}
    for f in files:
        for p in json.loads(f.read_text()):
            by_slug[p['slug']] = (f, p)
    return files, by_slug


def write_shards(files, by_slug):
    grouped = defaultdict(list)
    for slug, (f, page) in by_slug.items():
        grouped[f].append(page)
    for f in files:
        f.write_text(json.dumps(grouped[f], ensure_ascii=False, separators=(',', ':')))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, default=DEFAULT_SOURCE,
                    help='Recovered HTML tree to walk')
    ap.add_argument('--since', type=str, default='',
                    help='Only ingest files mtime >= this (YYYY-MM-DD HH:MM, '
                         'or "now" / "0" for everything)')
    ap.add_argument('--apply', action='store_true',
                    help='Write changes into shards (otherwise dry-run)')
    ap.add_argument('--insert-new', action='store_true',
                    help='Insert pages whose slug is not in any shard yet')
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    if not args.source.is_dir():
        print(f'no source tree: {args.source}', file=sys.stderr)
        return 2

    if args.since in ('', '0'):
        cutoff = 0.0
    elif args.since == 'now':
        cutoff = time.time()
    else:
        cutoff = time.mktime(time.strptime(args.since, '%Y-%m-%d %H:%M'))

    files, by_slug = load_shards()
    print(f'loaded {len(by_slug)} slugs across {len(files)} shards',
          file=sys.stderr)

    log: list[dict] = []
    updated = 0
    inserted = 0
    skipped_old = 0
    skipped_no_body = 0
    skipped_unknown = 0
    n_seen = 0

    for ap_root, _dn, fns in __import__('os').walk(args.source):
        for fn in fns:
            if not fn.endswith(('.html', '.htm')):
                continue
            fp = Path(ap_root) / fn
            if fp.stat().st_mtime < cutoff:
                skipped_old += 1
                continue
            n_seen += 1
            rel = str(fp.relative_to(args.source))
            url_path = file_to_url_path(rel)
            slug = primary_slug(url_path) or 'index'

            title, body = extract(fp)
            if not body:
                skipped_no_body += 1
                continue

            existing = by_slug.get(slug)
            if existing is None:
                if not args.insert_new:
                    skipped_unknown += 1
                    log.append({'rel': rel, 'slug': slug, 'status': 'unknown-slug'})
                    continue
                # Insert into smallest shard for balance
                target_file = min(files, key=lambda x: x.stat().st_size)
                page = {
                    'slug': slug,
                    'title': title or slug,
                    'body_html': body,
                    'aliases': [],
                }
                by_slug[slug] = (target_file, page)
                inserted += 1
                log.append({'rel': rel, 'slug': slug, 'status': 'inserted',
                            'bytes': len(body)})
            else:
                f, page = existing
                page['body_html'] = body
                if title:
                    page['title'] = title
                updated += 1
                log.append({'rel': rel, 'slug': slug, 'status': 'updated',
                            'bytes': len(body)})

            if args.limit and (updated + inserted) >= args.limit:
                break
        if args.limit and (updated + inserted) >= args.limit:
            break

    print(f'\nseen={n_seen}  updated={updated}  inserted={inserted}',
          file=sys.stderr)
    print(f'skipped: old={skipped_old} no-body={skipped_no_body} '
          f'unknown-slug={skipped_unknown}', file=sys.stderr)

    LOG.write_text(json.dumps(log, ensure_ascii=False))
    print(f'log: {LOG}', file=sys.stderr)

    if args.apply and (updated or inserted):
        write_shards(files, by_slug)
        print(f'wrote {len(files)} shards', file=sys.stderr)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
