#!/usr/bin/env python3
"""Clean up pages.json titles and body_html.

Fixes:
  1. Strip trailing " | IT for Change" from titles (Site.astro re-appends).
  2. Drop the first <h1> in body_html when it duplicates page.title
     ([...slug].astro renders its own h1).
  3. Remove on*= event handlers left over from Drupal admin scripts.
  4. Rewrite https://(annual-reports|projects).itforchange.net/* → /<sub>/*
  5. Rewrite https://(www.)?itforchange.net/* → /*
  6. Rewrite /index.php/<slug> hrefs to /<slug> when the slug exists.
  7. Rewrite surviving /node/<id> hrefs via the node-id → slug map.

Idempotent. Pass --apply to write back; default is dry-run.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES_JSON = ROOT / 'src' / 'data' / 'pages.json'

# --- regexes ---------------------------------------------------------

TITLE_SUFFIX_RE = re.compile(r'\s*\|\s*IT\s*for\s*Change\s*$', re.I)

# Match the FIRST <h1>...</h1> in body_html, allowing reasonable
# wrappers (divs / anchors) before it. We deliberately don't try to
# parse the whole DOM; we just need to find the very first <h1>.
LEAD_H1_RE = re.compile(r'<h1[^>]*>(.*?)</h1>\s*', re.S | re.I)
LEAD_H1_PREFIX = re.compile(r'^(?:\s*<(?:div|a|span|section)\b[^>]*>\s*)*', re.I)

ONHANDLER_RE = re.compile(
    r'''\s+on(?:click|load|mouseover|mouseout|focus|blur|change|submit)'''
    r'''=(?:"[^"]*"|'[^']*')''',
    re.I,
)

SUBDOMAIN_HREF_RE = re.compile(
    r'(href|src)="https?://(annual-reports|projects)\.itforchange\.net/?', re.I
)
APEX_HREF_RE = re.compile(
    r'(href|src)="https?://(?:www\.)?itforchange\.net/?', re.I
)

INDEX_PHP_HREF_RE = re.compile(
    r'href="/?index\.php/([^"#?]+)([#?][^"]*)?"', re.I
)
NODE_HREF_RE = re.compile(r'href="/?node/(\d+)([#?][^"]*)?"', re.I)


# --- transforms (each returns (new_value, changed_bool)) ------------

def fix_title(title: str) -> tuple[str, bool]:
    nt = TITLE_SUFFIX_RE.sub('', title).strip()
    # Some legacy Joomla pages serialised the <title> twice ("about
    # usabout us"). Collapse exact halve-and-repeat duplicates.
    half = len(nt) // 2
    if half >= 4 and nt[:half].strip() == nt[half:].strip():
        nt = nt[:half].strip()
    return (nt, nt != title) if nt else (title, False)


def drop_leading_h1(body: str, page_title: str) -> tuple[str, bool]:
    """Remove the first <h1> if it duplicates page_title (prefix match)."""
    prefix = LEAD_H1_PREFIX.match(body)
    head_end = prefix.end() if prefix else 0
    m = LEAD_H1_RE.search(body, head_end)
    if not m:
        return body, False
    inner = re.sub(r'<[^>]+>', '', m.group(1)).strip().lower()
    title_norm = page_title.strip().lower()
    if not title_norm or not inner.startswith(title_norm[:30]):
        return body, False
    return body[: m.start()] + body[m.end():], True


def strip_event_handlers(body: str) -> tuple[str, bool]:
    nb = ONHANDLER_RE.sub('', body)
    return nb, nb != body


def rewrite_subdomain(body: str) -> tuple[str, int]:
    n = [0]
    def repl(m: re.Match) -> str:
        n[0] += 1
        return f'{m.group(1)}="/{m.group(2)}/'
    return SUBDOMAIN_HREF_RE.sub(repl, body), n[0]


def rewrite_apex(body: str) -> tuple[str, int]:
    n = [0]
    def repl(m: re.Match) -> str:
        n[0] += 1
        return f'{m.group(1)}="/'
    return APEX_HREF_RE.sub(repl, body), n[0]


def rewrite_index_php(body: str, by_slug: set[str], aliases: dict[str, str]) -> tuple[str, int, int]:
    ok = [0]
    miss = [0]
    def repl(m: re.Match) -> str:
        tail, anchor = m.group(1), m.group(2) or ''
        if tail in by_slug:
            ok[0] += 1
            return f'href="/{tail}{anchor}"'
        canonical = aliases.get(tail)
        if canonical:
            ok[0] += 1
            return f'href="/{canonical}{anchor}"'
        miss[0] += 1
        return m.group(0)
    return INDEX_PHP_HREF_RE.sub(repl, body), ok[0], miss[0]


def rewrite_node(body: str, node_to_slug: dict[str, str]) -> tuple[str, int, int]:
    ok = [0]
    miss = [0]
    def repl(m: re.Match) -> str:
        nid, anchor = m.group(1), m.group(2) or ''
        slug = node_to_slug.get(nid)
        if slug:
            ok[0] += 1
            return f'href="/{slug}{anchor}"'
        miss[0] += 1
        return m.group(0)
    return NODE_HREF_RE.sub(repl, body), ok[0], miss[0]


# --- driver ----------------------------------------------------------

def build_lookup(pages: list[dict]) -> tuple[set[str], dict[str, str], dict[str, str]]:
    by_slug = {p['slug'] for p in pages}
    aliases: dict[str, str] = {}
    for p in pages:
        for a in p.get('aliases') or []:
            a = a.lstrip('/')
            aliases[a] = p['slug']
            # Strip a leading "index.php/" so we can match clean tails too
            if a.startswith('index.php/'):
                aliases[a[len('index.php/'):]] = p['slug']
    # Build node-id → slug from any alias containing /node/N
    node_to_slug: dict[str, str] = {}
    node_re = re.compile(r'(?:^|/)node/(\d+)$')
    for a, s in aliases.items():
        m = node_re.search(a)
        if m:
            node_to_slug[m.group(1)] = s
    return by_slug, aliases, node_to_slug


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    pages = json.loads(PAGES_JSON.read_text())
    by_slug, aliases, node_to_slug = build_lookup(pages)
    print(f'pages={len(pages)}  aliases={len(aliases)}  node_ids={len(node_to_slug)}')

    counts: Counter[str] = Counter()
    for p in pages:
        new_title, changed = fix_title(p['title'])
        counts['title_dedup'] += int(changed)
        if changed:
            p['title'] = new_title

        b = p.get('body_html') or ''

        b, changed = drop_leading_h1(b, p['title'])
        counts['h1_drop'] += int(changed)

        b, changed = strip_event_handlers(b)
        counts['onhandler'] += int(changed)

        b, n = rewrite_subdomain(b);     counts['subdomain']         += n
        b, n = rewrite_apex(b);          counts['apex']              += n
        b, ok, miss = rewrite_index_php(b, by_slug, aliases)
        counts['index_php_rewrite']     += ok
        counts['index_php_unresolved']  += miss
        b, ok, miss = rewrite_node(b, node_to_slug)
        counts['node_rewrite']     += ok
        counts['node_unresolved']  += miss

        p['body_html'] = b

    print('\nchanges:')
    for k, n in counts.most_common():
        print(f'  {k:24s} {n}')

    if args.apply:
        PAGES_JSON.write_text(
            json.dumps(pages, ensure_ascii=False, separators=(',', ':'))
        )
        print(f'\nwrote {PAGES_JSON} ({PAGES_JSON.stat().st_size/1024/1024:.1f} MB)')
    else:
        print('\n(dry-run; pass --apply to write)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
