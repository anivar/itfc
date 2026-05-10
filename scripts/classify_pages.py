#!/usr/bin/env python3
"""Deep relevance classification of pages.json entries.

Each page is assigned to the FIRST matching bucket below. Order matters:
junk-shape checks run before content checks so a near-empty admin page
gets bucketed by URL, not by emptiness.

Buckets:
  junk_slug         slug we already filter out at render time
                    (index, contains ?, =, starts index.php/, '\n')
  duplicate_slug    second-or-later page with the same case-insensitive
                    slug (the first wins)
  drupal_admin      /admin/, /node/add/, /user/login, /user/register,
                    /user/N/edit, /comment/reply, /search, /filter/tips
  user_profile      /user/N (Drupal user pages, no real content)
  comment_thread    slug starts with comment/ or contains #comment-
  print_view        /print/, ?print=
  feed              /rss.xml, /atom.xml, slug ends .xml or /feed
  paginated_view    Drupal Views pager: trailing /N or /page/N
  taxonomy_stub     /taxonomy/term/N or /category/* with body < 400B text
  mediawiki_special MediaWiki Special:* / index.php?title=Special:*
  wayback_error     body says page-not-in-wayback / Hrm.
  not_found_html    body looks like an HTTP 404 / "page not found"
  redirect_only     body is just a meta-refresh or single short link
  empty             body_html missing / whitespace
  near_empty        text content < 60 chars after stripping tags
  template_only     legacy Joomla page-frame, low text density
  duplicate_body    body_html is byte-identical to a previous page
  ok                everything else — real content

Writes scripts/_classified.json: {slug: bucket}.
Writes scripts/_classified_report.json: per-bucket aggregate counts +
inbound link totals so prune_pages.py can decide what's safe to drop.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_JSON = ROOT / 'src' / 'data' / 'pages.json'
OUT = Path(__file__).resolve().parent / '_classified.json'
REPORT = Path(__file__).resolve().parent / '_classified_report.json'

TAG_RE = re.compile(r'<[^>]+>')
WS_RE = re.compile(r'\s+')
META_REFRESH_RE = re.compile(r'<meta[^>]+http-equiv\s*=\s*["\']?refresh', re.I)

JOOMLA_MARKERS = (
    'class="moduletable',
    'mainlevel-nav',
    'class="contentpaneopen',
    'componentheading',
    'biz_blue_ii',
)

JUNK_SLUG_RE = re.compile(r'^index$|[?=\n]|^index\.php/', re.I)
ADMIN_SLUG_RE = re.compile(
    r'^(admin(?:/|$)|node/add|user/login|user/register|user/\d+/edit'
    r'|comment/reply|search(?:/|$)|filter/tips)', re.I)
USER_SLUG_RE = re.compile(r'^user/\d+/?$', re.I)
COMMENT_SLUG_RE = re.compile(r'^comment/|#comment-', re.I)
PRINT_SLUG_RE = re.compile(r'^print/|[?&]print=', re.I)
FEED_SLUG_RE = re.compile(r'\.xml$|/(rss|atom|feed)$', re.I)
PAGINATED_SLUG_RE = re.compile(r'(?:^|/)(?:page|all)/?\d+$|[?&]page=\d+', re.I)
TAXONOMY_SLUG_RE = re.compile(r'^(taxonomy/term/\d+|category/.+)$', re.I)
MEDIAWIKI_SPECIAL_RE = re.compile(
    r'(?:^|/)(?:index\.php\?title=)?Special:|/Special:[A-Z]', re.I)

WAYBACK_ERROR_MARKERS = (
    'Hrm.',
    'machine has not archived that URL',
    'page is not available',
    'wayback-toolbar-error',
)
NOT_FOUND_MARKERS = (
    'Page not found',
    '404 Not Found',
    'The requested URL was not found',
    'The requested page could not be found',
)


def text_density(body: str) -> tuple[int, float]:
    text = WS_RE.sub(' ', TAG_RE.sub(' ', body)).strip()
    return len(text), len(text) / max(len(body), 1)


def bucket(p: dict, seen_slugs: set[str], seen_bodies: set[str]) -> str:
    slug = p.get('slug', '') or ''
    body = p.get('body_html') or ''

    # ---- URL-shape buckets first (do not look at body) -----------------
    if JUNK_SLUG_RE.search(slug):
        return 'junk_slug'
    sl = slug.casefold()
    if sl in seen_slugs:
        return 'duplicate_slug'

    if ADMIN_SLUG_RE.match(slug):
        return 'drupal_admin'
    if USER_SLUG_RE.match(slug):
        return 'user_profile'
    if COMMENT_SLUG_RE.search(slug):
        return 'comment_thread'
    if PRINT_SLUG_RE.search(slug):
        return 'print_view'
    if FEED_SLUG_RE.search(slug):
        return 'feed'
    if PAGINATED_SLUG_RE.search(slug):
        return 'paginated_view'
    if MEDIAWIKI_SPECIAL_RE.search(slug):
        return 'mediawiki_special'

    # ---- Body-content buckets ------------------------------------------
    if not body.strip():
        return 'empty'
    text_len, density = text_density(body)
    if text_len < 60:
        return 'near_empty'

    if any(m in body for m in WAYBACK_ERROR_MARKERS) and text_len < 400:
        return 'wayback_error'
    if any(m in body for m in NOT_FOUND_MARKERS) and text_len < 600:
        return 'not_found_html'
    if META_REFRESH_RE.search(body) and text_len < 200:
        return 'redirect_only'

    if TAXONOMY_SLUG_RE.match(slug) and text_len < 400:
        return 'taxonomy_stub'

    joomla_hits = sum(1 for m in JOOMLA_MARKERS if m in body)
    if joomla_hits >= 2 and density < 0.18:
        return 'template_only'

    body_hash = hashlib.sha1(body.encode('utf-8', 'replace')).hexdigest()
    if body_hash in seen_bodies:
        return 'duplicate_body'
    seen_bodies.add(body_hash)

    return 'ok'


def inbound_counts(pages: list[dict], targets: set[str]) -> dict[str, int]:
    """Count how many other pages link to each target slug."""
    counts = {s: 0 for s in targets}
    if not targets:
        return counts
    rx = {s: re.compile(rf'href="/?{re.escape(s)}(?:["#?])') for s in targets}
    for p in pages:
        body = p.get('body_html') or ''
        for s, r in rx.items():
            if r.search(body):
                counts[s] += 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--samples', type=int, default=8)
    args = ap.parse_args()

    pages = json.loads(PAGES_JSON.read_text())

    seen_slugs: set[str] = set()
    seen_bodies: set[str] = set()
    classified: dict[str, str] = {}
    counts: Counter[str] = Counter()
    samples: dict[str, list[tuple[str, int]]] = defaultdict(list)

    for p in pages:
        b = bucket(p, seen_slugs, seen_bodies)
        seen_slugs.add(p.get('slug', '').casefold())
        classified[p['slug']] = b
        counts[b] += 1
        if b != 'ok' and len(samples[b]) < 50:
            samples[b].append((p['slug'], len(p.get('body_html') or '')))

    # Inbound link audit for non-ok pages
    flagged = {s for s, b in classified.items() if b != 'ok'}
    inbound = inbound_counts(pages, flagged)

    OUT.write_text(json.dumps(classified, ensure_ascii=False))

    report: dict[str, dict] = {}
    total = sum(counts.values())
    print(f'classified {total} pages\n')
    print(f'  {"bucket":18s} {"count":>5s}  {"%":>5s}  {"refd":>5s}  {"orph":>5s}')
    print(f'  {"-"*18} {"-"*5}  {"-"*5}  {"-"*5}  {"-"*5}')
    for b, n in counts.most_common():
        flagged_in_bucket = [s for s in flagged if classified[s] == b]
        refd = sum(1 for s in flagged_in_bucket if inbound[s] > 0)
        orph = len(flagged_in_bucket) - refd
        report[b] = {
            'count': n,
            'referenced': refd,
            'orphaned': orph,
        }
        if b == 'ok':
            print(f'  {b:18s} {n:5d}  {100*n/total:5.1f}')
        else:
            print(f'  {b:18s} {n:5d}  {100*n/total:5.1f}  {refd:5d}  {orph:5d}')

    print('\nlegend: refd = at least one inbound link from another page; '
          'orph = zero inbound')

    print('\nsamples (slug, body_html bytes, inbound):')
    for b, _ in counts.most_common():
        if b == 'ok':
            continue
        rows = samples[b][: args.samples]
        if not rows:
            continue
        print(f'\n  [{b}]')
        rows = sorted(rows, key=lambda x: -inbound.get(x[0], 0))
        for s, sz in rows:
            n = inbound.get(s, 0)
            print(f'    inbound={n:4d}  {sz:7d}B  {s}')

    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
