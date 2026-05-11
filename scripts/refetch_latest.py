#!/usr/bin/env python3
"""Refetch the latest Wayback captures for a list of slugs.

For each input path:
  1. Query the Wayback CDX API for the most recent capture
  2. Fetch it via the `id_` raw envelope (no Wayback chrome injected)
  3. Extract body_html with the same heuristics as import_cc_content.py
  4. Update / insert the corresponding entry in src/data/pages/*.json,
     keeping aliases and existing-slug membership intact

The seed list comes from --seed-html (extracts internal hrefs from one
captured HTML file) or --paths-file (one path per line). Output:
  - per-shard JSON updated in place
  - scripts/_refetch.json — log of {path, ts, source_url, status}
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARDS_DIR = ROOT / 'src' / 'data' / 'pages'
LOG = Path(__file__).resolve().parent / '_refetch.json'
CHECKPOINT = Path(__file__).resolve().parent / '_refetch_done.json'

CDX_URL = 'https://web.archive.org/cdx/search/cdx'
WB_BASE = 'https://web.archive.org/web'
UA = 'itfc-archive-refetch/1.0 (+anivar@foodhub.com)'

INTERNAL_PREFIXES = (
    'https://itforchange.net',
    'http://itforchange.net',
    'https://www.itforchange.net',
    'http://www.itforchange.net',
)


# ---------- HTML helpers ------------------------------------------------

class _Body(HTMLParser):
    """Capture inner HTML of the first matching content container."""
    PRIORITY = ('main', 'article')

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []
        self.capture_at: int | None = None
        self.target_tag: str | None = None
        self.buf: list[str] = []
        self.found: dict[str, str] = {}
        self.title: str | None = None
        self._title_capturing = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'title':
            self._title_capturing = True
        if self.capture_at is None:
            cls = a.get('class') or ''
            if (
                tag == 'div' and a.get('id') == 'content'
            ) or (
                tag == 'div' and 'region-content' in cls
            ) or (
                # Joomla 1.5 legacy pages (pre-Drupal /events/*.html era)
                # used a table-based layout; the body is the first
                # <table class="contentpaneopen">.
                tag == 'table' and 'contentpaneopen' in cls
            ) or tag in self.PRIORITY:
                self.capture_at = len(self.stack)
                self.target_tag = tag
                self.buf = []
        if self.capture_at is not None:
            attrs_str = ''.join(f' {k}="{v}"' for k, v in attrs)
            self.buf.append(f'<{tag}{attrs_str}>')
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        if self.capture_at is not None:
            self.buf.append(f'</{tag}>')
            if (
                len(self.stack) == self.capture_at
                and tag == self.target_tag
                and self.target_tag is not None
            ):
                # Tables (Joomla 1.5 layout) come in pairs — title table +
                # body table both have class="contentpaneopen". Concatenate
                # so the whole content area is captured. Other targets keep
                # first-match semantics.
                key = self.target_tag
                if key == 'table' and key in self.found:
                    self.found[key] = self.found[key] + ''.join(self.buf)
                else:
                    self.found.setdefault(key, ''.join(self.buf))
                self.capture_at = None
                self.target_tag = None
                self.buf = []
        if tag == 'title':
            self._title_capturing = False

    def handle_data(self, data):
        if self._title_capturing and self.title is None:
            self.title = data.strip()
        if self.capture_at is not None:
            self.buf.append(data)

    def handle_entityref(self, name):
        if self.capture_at is not None:
            self.buf.append(f'&{name};')

    def handle_charref(self, name):
        if self.capture_at is not None:
            self.buf.append(f'&#{name};')


def extract_body_and_title(html_text: str) -> tuple[str, str | None]:
    p = _Body()
    p.feed(html_text)
    for tag in ('div', 'main', 'article', 'table'):
        if tag in p.found:
            inner = p.found[tag]
            # Strip outer wrapper to keep only inner content
            inner = re.sub(rf'^<{tag}\b[^>]*>', '', inner)
            inner = re.sub(rf'</{tag}>$', '', inner)
            return inner.strip(), p.title
    return '', p.title


def normalize_internal(html_text: str) -> str:
    """Collapse absolute itforchange.net URLs to root-relative paths."""
    out = html_text
    out = re.sub(
        r'https?://(?:www\.)?itforchange\.net/?',
        '/',
        out,
        flags=re.I,
    )
    out = re.sub(
        r'https?://annual-reports\.itforchange\.net/?',
        '/annual-reports/',
        out,
        flags=re.I,
    )
    out = re.sub(
        r'https?://projects\.itforchange\.net/?',
        '/projects/',
        out,
        flags=re.I,
    )
    return out


# ---------- Wayback CDX -------------------------------------------------

def fetch_url(url: str, timeout: int = 30, max_retries: int = 5) -> bytes:
    """GET with simple exponential backoff for 429/5xx."""
    import urllib.error
    backoff = 2.0
    last_err: Exception | None = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 502, 503, 504):
                wait = backoff * (2 ** attempt)
                print(f'  HTTP {e.code} — sleep {wait:.0f}s', file=sys.stderr)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            wait = backoff * (2 ** attempt)
            print(f'  net err {e} — sleep {wait:.0f}s', file=sys.stderr)
            time.sleep(wait)
            continue
    raise last_err if last_err else RuntimeError('fetch_url failed')


def latest_capture(target_url: str) -> tuple[str, str] | None:
    """Return (timestamp, original_url) for the latest 200 capture, or None."""
    qs = urllib.parse.urlencode({
        'url': target_url,
        'output': 'json',
        'filter': 'statuscode:200',
        'fl': 'timestamp,original',
        'limit': '-1',
    })
    try:
        data = fetch_url(f'{CDX_URL}?{qs}')
    except Exception as e:
        print(f'  CDX error: {e}', file=sys.stderr)
        return None
    try:
        rows = json.loads(data)
    except json.JSONDecodeError as e:
        print(f'  CDX returned non-JSON ({len(data)}B): {e}', file=sys.stderr)
        return None
    if len(rows) <= 1:
        return None
    ts, original = rows[-1]
    return ts, original


def fetch_capture(ts: str, original: str) -> str:
    raw_url = f'{WB_BASE}/{ts}id_/{original}'
    body = fetch_url(raw_url, timeout=60)
    return body.decode('utf-8', errors='replace')


# ---------- Path discovery ---------------------------------------------

def extract_paths_from_html(html_text: str) -> list[str]:
    paths: set[str] = set()
    for m in re.finditer(r'href=["\']([^"\'#?]+)', html_text):
        href = m.group(1)
        if href.startswith('//'):
            continue
        if href.startswith('/') and not href.startswith('/static/'):
            paths.add(href)
            continue
        # Wayback-wrapped form
        m2 = re.match(r'https?://web\.archive\.org/web/[^/]+/(https?://[^\s"\'<>]+)', href, re.I)
        if m2:
            href = m2.group(1)
        for prefix in INTERNAL_PREFIXES:
            if href.lower().startswith(prefix):
                tail = href[len(prefix):] or '/'
                paths.add(tail)
                break
    return sorted(paths)


def is_content_path(path: str) -> bool:
    """Filter out asset / admin / pager paths."""
    p = path.lower()
    if any(p.startswith(s) for s in (
        '/core/', '/sites/default/files/', '/themes/',
        '/modules/', '/sites/', '/misc/', '/profile/', '/static/',
        '/admin/', '/user/login', '/user/register', '/cron',
    )):
        return False
    if p.endswith(('.css', '.js', '.ico', '.png', '.jpg', '.jpeg',
                   '.gif', '.svg', '.woff', '.woff2', '.ttf', '.pdf',
                   '.xml')):
        return False
    if 'mailto:' in p or 'javascript:' in p:
        return False
    return True


# ---------- Shard updater ---------------------------------------------

def slug_from_path(path: str) -> str:
    s = path.lstrip('/')
    s = s.split('?', 1)[0].split('#', 1)[0]
    return s.rstrip('/')


def load_shards() -> tuple[list[Path], dict[str, tuple[Path, dict]]]:
    files = sorted(SHARDS_DIR.glob('*.json'))
    by_slug: dict[str, tuple[Path, dict]] = {}
    for f in files:
        for p in json.loads(f.read_text()):
            by_slug[p['slug']] = (f, p)
    return files, by_slug


def write_shards(files: list[Path], by_slug: dict[str, tuple[Path, dict]]) -> None:
    grouped: dict[Path, list[dict]] = defaultdict(list)
    for slug, (f, page) in by_slug.items():
        grouped[f].append(page)
    for f in files:
        f.write_text(
            json.dumps(grouped[f], ensure_ascii=False, separators=(',', ':'))
        )


# ---------- Main --------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed-html', type=Path,
                    help='Captured HTML file whose hrefs seed the path list')
    ap.add_argument('--paths-file', type=Path,
                    help='File with one URL path per line')
    ap.add_argument('--also-seed-path', action='append', default=[],
                    help='Extra paths to include (e.g. /)')
    ap.add_argument('--apply', action='store_true',
                    help='Write fetched bodies into shards')
    ap.add_argument('--sleep', type=float, default=1.0,
                    help='Delay between Wayback requests, seconds')
    ap.add_argument('--limit', type=int, default=0,
                    help='Cap the number of fetches (0 = no cap)')
    ap.add_argument('--homepage-html', type=Path,
                    help='Local file to use as the / capture (skips CDX)')
    ap.add_argument('--dedupe-via-redirects', action='store_true',
                    help='Drop seed paths whose canonical form is also in the seed list')
    ap.add_argument('--all-slugs', action='store_true',
                    help='Seed paths from every slug already in src/data/pages')
    ap.add_argument('--resume', action='store_true',
                    help='Skip paths recorded as ok in the checkpoint file')
    ap.add_argument('--checkpoint-every', type=int, default=10,
                    help='Flush checkpoint + log to disk every N processed paths')
    args = ap.parse_args()

    done_ok: set[str] = set()
    if args.resume and CHECKPOINT.exists():
        try:
            done_ok = set(json.loads(CHECKPOINT.read_text()))
            print(f'resume: skipping {len(done_ok)} already-ok paths')
        except Exception:
            pass

    seeds: list[str] = []
    if args.seed_html and args.seed_html.is_file():
        seeds.extend(extract_paths_from_html(args.seed_html.read_text()))
    if args.paths_file and args.paths_file.is_file():
        seeds.extend(args.paths_file.read_text().splitlines())
    if args.all_slugs:
        for f in sorted(SHARDS_DIR.glob('*.json')):
            for p in json.loads(f.read_text()):
                s = p.get('slug')
                if s and s != 'index':
                    seeds.append('/' + s)
                elif s == 'index':
                    seeds.append('/')
    seeds.extend(args.also_seed_path)
    seeds = sorted({s.strip() for s in seeds if s.strip()})
    seeds = [s for s in seeds if is_content_path(s)]

    if args.dedupe_via_redirects:
        rmap_file = ROOT / 'src' / 'data' / 'redirects.json'
        if rmap_file.exists():
            rmap = json.loads(rmap_file.read_text())
            canonicalized = []
            for p in seeds:
                canon = rmap.get(p, p)
                canonicalized.append(canon)
            seeds = sorted(set(canonicalized))

    if done_ok:
        seeds = [s for s in seeds if s not in done_ok]
    if args.limit:
        seeds = seeds[: args.limit]
    print(f'paths to refetch: {len(seeds)}')

    files, by_slug = load_shards()
    log: list[dict] = []
    updated = 0
    inserted = 0

    def flush() -> None:
        LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2))
        CHECKPOINT.write_text(json.dumps(sorted(done_ok), ensure_ascii=False))
        if args.apply and (updated or inserted):
            write_shards(files, by_slug)

    for i, path in enumerate(seeds, 1):
        target = f'https://itforchange.net{path}' if path.startswith('/') else f'https://itforchange.net/{path}'
        slug = slug_from_path(path) or 'index'
        print(f'[{i:3d}/{len(seeds)}] {slug}', end=' ', flush=True)

        # Special case: homepage / from a local file (CDX often times
        # out for the bare apex URL; we already have the latest capture).
        if path in ('/', '') and args.homepage_html and args.homepage_html.is_file():
            html_text = args.homepage_html.read_text()
            ts = 'local'
            print('-> using --homepage-html', end=' ')
        else:
            cap = latest_capture(target)
            if cap is None:
                print('-> no capture')
                log.append({'path': path, 'status': 'no-capture'})
                if args.checkpoint_every and i % args.checkpoint_every == 0:
                    flush()
                time.sleep(args.sleep)
                continue
            ts, original = cap
            try:
                html_text = fetch_capture(ts, original)
            except Exception as e:
                print(f'-> fetch error: {e}')
                log.append({'path': path, 'ts': ts, 'status': f'error: {e}'})
                if args.checkpoint_every and i % args.checkpoint_every == 0:
                    flush()
                time.sleep(args.sleep)
                continue
        body, title = extract_body_and_title(html_text)
        if not body:
            print(f'-> ts={ts} but no extractable body ({len(html_text)}B)')
            log.append({'path': path, 'ts': ts, 'status': 'no-body'})
            if args.checkpoint_every and i % args.checkpoint_every == 0:
                flush()
            time.sleep(args.sleep)
            continue
        body = normalize_internal(body)
        log.append({
            'path': path, 'ts': ts, 'slug': slug,
            'bytes': len(body), 'title': title or '',
            'status': 'ok',
        })
        done_ok.add(path)
        if args.apply:
            existing = by_slug.get(slug)
            if existing is not None:
                f, page = existing
                page['body_html'] = body
                if title:
                    page['title'] = title
                updated += 1
                print(f'-> updated ({len(body)}B, ts={ts})')
            else:
                # New slug: drop into the smallest shard for balance
                target_file = min(files, key=lambda x: x.stat().st_size)
                page = {
                    'slug': slug,
                    'title': title or slug,
                    'body_html': body,
                    'aliases': [],
                }
                by_slug[slug] = (target_file, page)
                inserted += 1
                print(f'-> inserted ({len(body)}B, ts={ts})')
        else:
            print(f'-> ts={ts}, {len(body)}B (dry-run)')
        if args.checkpoint_every and i % args.checkpoint_every == 0:
            flush()
        time.sleep(args.sleep)

    flush()
    print(f'\nlog: {LOG}')
    print(f'checkpoint: {CHECKPOINT}')
    print(f'updated={updated} inserted={inserted}')
    if args.apply:
        print(f'wrote {len(files)} shards')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
