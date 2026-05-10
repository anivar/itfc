#!/usr/bin/env python3
"""Post-process pages.json + redirects.json after import.

- Drop junk slugs that are query-string artifacts (?...= leftovers from
  Drupal listing pagination).
- Build node-id -> slug map from aliases, then rewrite /node/N references
  inside body_html to point at the canonical slug. Unresolved /node/N
  refs are left alone (so the 404 still surfaces).
- Mirror the same drops into redirects.json so dead targets don't 302.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / 'src' / 'data' / 'pages.json'
REDIRECTS = ROOT / 'src' / 'data' / 'redirects.json'

NODE_ALIAS_RE = re.compile(r'^(?:.*/)?node/(\d+)$')
NODE_HREF_RE = re.compile(r'(href|src)="(/node/(\d+))(\?[^"]*)?"', re.IGNORECASE)


def is_junk_slug(slug: str) -> bool:
    if not slug:
        return True
    if slug.startswith('?') or slug.startswith('&'):
        return True
    if slug.startswith('index.php/'):
        return True
    # Tokens that only appear in Drupal listing query params
    if any(tok in slug for tok in ('field_publication_type_target_id', 'thematic_areas_target_id',
                                    'field_author_value', 'field_year_value', 'page=')):
        return True
    return False


def main() -> int:
    pages = json.loads(PAGES.read_text())
    redirects = json.loads(REDIRECTS.read_text())

    # 1. Drop junk pages
    before = len(pages)
    kept = [p for p in pages if not is_junk_slug(p.get('slug', ''))]
    dropped_slugs = {p['slug'] for p in pages if is_junk_slug(p.get('slug', ''))}
    print(f'dropped {before - len(kept)} junk pages (kept {len(kept)})')

    # 2. Build node -> slug map from aliases of kept pages
    node_to_slug: dict[str, str] = {}
    for p in kept:
        for a in p.get('aliases', []) or []:
            m = NODE_ALIAS_RE.match(a)
            if m:
                node_to_slug.setdefault(m.group(1), p['slug'])
    print(f'node->slug entries: {len(node_to_slug)}')

    # 3. Rewrite body_html /node/N -> /slug when known
    rewrites = 0
    def repl(m: re.Match) -> str:
        attr, _full, nid, qs = m.group(1), m.group(2), m.group(3), m.group(4) or ''
        slug = node_to_slug.get(nid)
        if not slug:
            return m.group(0)
        nonlocal rewrites
        rewrites += 1
        return f'{attr}="/{slug}{qs}"'

    for p in kept:
        if 'body_html' in p and p['body_html']:
            new_body = NODE_HREF_RE.sub(repl, p['body_html'])
            if new_body is not p['body_html']:
                p['body_html'] = new_body
    print(f'body_html /node/N rewrites: {rewrites}')

    # 4. Rebuild redirects from aliases of kept pages.
    #    Aliases like `index.php/foo` and `node/123` are legitimate redirect
    #    sources; only drop ones that contain query-string artifacts.
    def bad_alias(a: str) -> bool:
        if not a:
            return True
        return any(c in a for c in ('?', '&', '='))

    cleaned: dict[str, str] = {}
    for p in kept:
        slug = p['slug']
        dst = '/' if slug == 'index' else f'/{slug}'
        for a in p.get('aliases', []) or []:
            if bad_alias(a):
                continue
            cleaned[f'/{a}'] = dst
    print(f'redirects rebuilt: {len(cleaned)}')

    PAGES.write_text(json.dumps(kept, ensure_ascii=False))
    REDIRECTS.write_text(json.dumps(cleaned, sort_keys=True, indent=0))
    print('wrote pages.json + redirects.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
