#!/usr/bin/env python3
"""Repair degraded titles on event pages.

Two pathologies show up in `src/data/pages/*.json`:

1. Drupal-template doubled titles like:
       "Welcome to IT for Change wsis iiwsis ii"
   The page name was concatenated twice with no separator. We collapse the
   trailing duplicate.

2. Joomla 1.5 captures whose <title> was just the site name
   ("Welcome to IT for Change") because Joomla rendered the real title
   inside the body, in <a class="contentpagetitle">…</a>. We promote that
   inner heading to the page title.

Idempotent: re-running is a no-op.

    python3 scripts/fix_event_titles.py [--apply]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

SHARDS = 'src/data/pages/*.json'

CONTENTPAGETITLE = re.compile(
    r'<a[^>]*class="contentpagetitle"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


SITE_PREFIX = 'Welcome to IT for Change'


def collapse_doubled_tail(title: str) -> str | None:
    """If title ends with the same word(s) twice with no separator, drop one,
    and strip the boilerplate "Welcome to IT for Change " site-name prefix
    when there is a real page name behind it.

    "Welcome to IT for Change wsis iiwsis ii" -> "wsis ii"
    "Networks | IT for Change"                -> None (unchanged)
    """
    m = re.match(r'^(.*?\s)([A-Za-z][\w]*(?:\s+[A-Za-z][\w]*)*)\2$', title)
    if not m:
        return None
    prefix, page = m.group(1).rstrip(), m.group(2).strip()
    if prefix == SITE_PREFIX and page:
        fixed = page
    else:
        fixed = f'{prefix} {page}'.strip()
    if fixed == title.strip():
        return None
    return fixed


def joomla_title_from_body(body: str) -> str | None:
    m = CONTENTPAGETITLE.search(body)
    if not m:
        return None
    raw = re.sub(r'<[^>]+>', '', m.group(1))
    raw = re.sub(r'\s+', ' ', raw).strip()
    return raw or None


SLUG_RE = re.compile(r'^events/(\d+)(?:-([\w-]+?))?(?:\.html)?$', re.IGNORECASE)


def event_id(slug: str) -> str | None:
    """events/52-wsis-ii.html -> '52'.  events/52 -> '52'.  Otherwise None."""
    m = SLUG_RE.match(slug.lower())
    return m.group(1) if m else None


def fix_page(p: dict, joomla_titles: dict[str, str]) -> tuple[bool, str]:
    """Returns (changed, reason)."""
    slug = (p.get('slug') or '').lower()
    if not (slug.startswith('events/') or slug == 'events'):
        return False, ''
    title = p.get('title') or ''
    body = p.get('body_html') or ''

    # 1. Joomla-quality title available for this event id? prefer it.
    eid = event_id(slug)
    if eid and eid in joomla_titles:
        good = joomla_titles[eid]
        if good and good.lower() != title.lower():
            p['title'] = good
            return True, f'promoted: -> {good!r}'

    # 2. Joomla page itself, but lookup didn't fire (e.g. unique id) — pull
    #    contentpagetitle from body.
    if title.strip() in ('Welcome to IT for Change', 'Welcome to IT for Change ',):
        better = joomla_title_from_body(body)
        if better and better.lower() != title.lower():
            p['title'] = better
            return True, f'joomla: -> {better!r}'

    # 3. Drupal doubled-tail fallback.
    fixed = collapse_doubled_tail(title)
    if fixed:
        p['title'] = fixed
        return True, f'doubled: -> {fixed!r}'

    return False, ''


def gather_joomla_titles() -> dict[str, str]:
    """Scan all shards and collect best title-per-event-id from Joomla pages."""
    out: dict[str, str] = {}
    for shard in sorted(glob.glob(SHARDS)):
        with open(shard, 'r', encoding='utf-8') as f:
            pages = json.load(f)
        for p in pages:
            slug = (p.get('slug') or '').lower()
            eid = event_id(slug)
            if not eid:
                continue
            body = p.get('body_html') or ''
            if 'contentpagetitle' not in body:
                continue
            t = joomla_title_from_body(body)
            if t:
                # Prefer the longest extracted title — duplicates across
                # slug variants usually agree, longer wins ties.
                cur = out.get(eid, '')
                if len(t) > len(cur):
                    out[eid] = t
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true',
                    help='Write shards. Default: dry-run with report only.')
    args = ap.parse_args()

    joomla_titles = gather_joomla_titles()
    print(f'gathered {len(joomla_titles)} joomla titles from contentpagetitle')
    if joomla_titles:
        for eid in sorted(joomla_titles)[:5]:
            print(f'  event #{eid}: {joomla_titles[eid]!r}')
        print('  ...')

    changed_shards: dict[str, int] = {}
    total = 0
    samples: list[str] = []
    for shard in sorted(glob.glob(SHARDS)):
        with open(shard, 'r', encoding='utf-8') as f:
            pages = json.load(f)
        n = 0
        for p in pages:
            ok, reason = fix_page(p, joomla_titles)
            if ok:
                n += 1
                total += 1
                if len(samples) < 12:
                    samples.append(f'{os.path.basename(shard)}  {p["slug"]:40s}  {reason}')
        if n and args.apply:
            with open(shard, 'w', encoding='utf-8') as f:
                json.dump(pages, f, ensure_ascii=False)
        if n:
            changed_shards[shard] = n

    print(f'pages fixed: {total}')
    for s, n in changed_shards.items():
        print(f'  {os.path.basename(s)}: {n}')
    print('samples:')
    for s in samples:
        print(f'  {s}')
    if not args.apply:
        print('\n(dry run; pass --apply to write)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
