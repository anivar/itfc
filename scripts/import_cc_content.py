#!/usr/bin/env python3
"""Import HTML corpora into the Astro project.

Walks one or more on-disk HTML trees (paths set via the SOURCES list below)
and emits two JSON files consumed at build time:

  src/data/pages.json     — array of {slug, title, body_html, aliases}
  src/data/redirects.json — {alias_path: canonical_path} → 302 redirects

Canonical selection:
  - Strip /index.php/ prefix to derive a "primary slug"
  - When multiple captures map to the same primary slug, prefer the one
    WITHOUT /index.php/, then the one without /node/, then the largest body
  - All non-canonical paths become aliases (→ 302 redirect via Astro
    `redirects` config)

Body sanitization: strip <html>/<head>/<script>/<style>/<nav>/<header>/<footer>;
keep the inner content of <div id="content"> / <main> / <article> / <body>
in that priority order. Absolute itforchange.net origins are normalized to
root-relative so the same payload renders under any deploy base.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

def _sources_from_env() -> list[tuple[str, Path]]:
    """Source HTML trees, configured via env (so paths aren't pinned in git).

    SOURCES env var: comma-separated `label=path` pairs, e.g.
        SOURCES="cc=/data/cc/itforchange.net,wayback=/data/wb/itforchange.net"
    Falls back to a developer-local default when unset.
    """
    raw = os.environ.get('SOURCES', '').strip()
    if raw:
        out: list[tuple[str, Path]] = []
        for part in raw.split(','):
            label, _, path = part.partition('=')
            label, path = label.strip(), path.strip()
            if label and path:
                out.append((label, Path(path)))
        if out:
            return out
    # Developer default: keep both common-crawl and wayback trees side by side
    return [
        ('common-crawl', Path.home() / 'itfc' / 'recovered_alt' / 'itforchange.net'),
        ('wayback', Path.home() / 'itfc' / 'recovered' / 'itforchange.net'),
    ]


SOURCES: list[tuple[str, Path]] = _sources_from_env()
PROJECT = Path(os.environ.get('PROJECT', Path(__file__).resolve().parent.parent))
DATA_DIR = PROJECT / 'src' / 'data'

NODE_RE = re.compile(r'(?:^|/)node/(\d+)(?:\.html)?$')
TAXO_RE = re.compile(r'(?:^|/)taxonomy/term/(\d+)(?:\.html)?$')

# ---------- HTML parsing ----------

VOID_TAGS = {'br', 'hr', 'img', 'input', 'meta', 'link', 'area', 'base',
             'col', 'embed', 'param', 'source', 'track', 'wbr'}


class ContentExtractor(HTMLParser):
    """Extract the inner HTML of the most-specific content container.

    Priority of containers (first match wins):
      1. <div id="content"> / <main id="content">
      2. <main>
      3. <article>
      4. <body> (fallback)

    Skip <script>, <style>, <noscript>, and Drupal admin/menu bars by tag name
    or class hint (toolbar, navbar, region-header, region-footer, sidebar).
    """

    SKIP_TAGS = {'script', 'style', 'noscript', 'iframe', 'svg'}
    SKIP_CLASS_HINTS = ('toolbar', 'admin-menu', 'navbar', 'region-header',
                         'region-footer', 'region-sidebar', 'block-menu',
                         'breadcrumb', 'comment-form', 'cookie-banner')

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        # Capture buffers per priority bucket
        self.buf: dict[str, list[str]] = {
            'content': [], 'main': [], 'article': [], 'body': []
        }
        # Stack entries: (tag, capture_key_active, skip_depth_active)
        self.stack: list[tuple[str, str | None, bool]] = []
        self.skip_depth = 0
        self.title_parts: list[str] = []
        self.in_title = False

    def _emit(self, s: str) -> None:
        if self.skip_depth:
            return
        # Append to ALL active capture buckets — each bucket is built from the
        # outermost-active-capture-tag inward.
        for _t, key, _skip in self.stack:
            if key:
                self.buf[key].append(s)

    def _bucket_for(self, tag: str, attrs_d: dict[str, str]) -> str | None:
        if tag == 'body':
            return 'body'
        if tag == 'article':
            return 'article'
        if tag == 'main':
            return 'main'
        if tag == 'div' and attrs_d.get('id') == 'content':
            return 'content'
        if tag == 'main' and attrs_d.get('id') == 'content':
            return 'content'
        if tag == 'div' and 'region-content' in (attrs_d.get('class') or ''):
            return 'content'
        return None

    def _should_skip(self, tag: str, attrs_d: dict[str, str]) -> bool:
        if tag in self.SKIP_TAGS:
            return True
        cls = (attrs_d.get('class') or '').lower()
        ident = (attrs_d.get('id') or '').lower()
        for hint in self.SKIP_CLASS_HINTS:
            if hint in cls or hint in ident:
                return True
        return False

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_d = {k: (v or '') for k, v in attrs}
        if tag == 'title':
            self.in_title = True
            return
        skip = self._should_skip(tag, attrs_d)
        bucket = self._bucket_for(tag, attrs_d) if not skip else None
        if skip:
            self.skip_depth += 1
            self.stack.append((tag, None, True))
            return
        # Emit the raw start tag into active buckets — but only AFTER
        # registering the bucket so the wrapping tag itself doesn't land in
        # its own buffer.
        self.stack.append((tag, bucket, False))
        if tag in VOID_TAGS:
            self._emit(self._render_starttag(tag, attrs_d, void=True))
            self.stack.pop()
            return
        if not bucket:
            self._emit(self._render_starttag(tag, attrs_d))

    def handle_endtag(self, tag: str) -> None:
        if tag == 'title':
            self.in_title = False
            return
        # Pop matching frame
        for i in range(len(self.stack) - 1, -1, -1):
            t, _, skip = self.stack[i]
            if t == tag:
                frame = self.stack.pop(i)
                if frame[2]:
                    self.skip_depth -= 1
                else:
                    if not frame[1]:
                        self._emit(f'</{tag}>')
                return

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
            return
        self._emit(html.escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if self.in_title:
            self.title_parts.append(f'&{name};')
            return
        self._emit(f'&{name};')

    def handle_charref(self, name: str) -> None:
        if self.in_title:
            self.title_parts.append(f'&#{name};')
            return
        self._emit(f'&#{name};')

    def _render_starttag(self, tag: str, attrs: dict[str, str], void: bool = False) -> str:
        parts = [tag]
        for k, v in attrs.items():
            if v == '':
                parts.append(k)
            else:
                v_esc = html.escape(v, quote=True)
                parts.append(f'{k}="{v_esc}"')
        return f'<{" ".join(parts)}{" /" if void else ""}>'

    def get_title(self) -> str:
        t = ''.join(self.title_parts).strip()
        return ' '.join(t.split())

    def get_body_html(self) -> str:
        for key in ('content', 'main', 'article', 'body'):
            if self.buf[key]:
                out = ''.join(self.buf[key]).strip()
                if out:
                    return out
        return ''


_ABS_ORIGIN_RE = re.compile(
    r'(?i)https?://(?:www\.)?itforchange\.net(?=/|"|\'|\s|$)'
)


def normalize_body_urls(body: str) -> str:
    """Normalize all URLs in body_html so the JSON is portable across hosts.

    - Strip absolute origins (https://itforchange.net, www variant) so links
      become root-relative. The renderer can then prefix the deploy BASE
      (e.g. /itfc/) at request time without re-importing.
    """
    return _ABS_ORIGIN_RE.sub('', body)


def extract(path: Path) -> tuple[str, str]:
    try:
        text = path.read_bytes().decode('utf-8', errors='replace')
    except Exception:
        return '', ''
    p = ContentExtractor()
    try:
        p.feed(text)
        p.close()
    except Exception:
        pass
    return p.get_title(), normalize_body_urls(p.get_body_html())


# ---------- canonical selection ----------

def file_to_url_path(rel: str) -> str:
    """Turn a relative file path into the URL path it represents."""
    p = rel
    if p.endswith('/index.html'):
        p = p[: -len('index.html')]
    elif p.endswith('.html'):
        p = p[:-5]
    elif p.endswith('.htm'):
        p = p[:-4]
    return p.rstrip('/')


def primary_slug(url_path: str) -> str:
    """Normalize away /index.php/ prefix to find equivalent paths."""
    s = url_path
    if s.startswith('index.php/'):
        s = s[len('index.php/'):]
    return s


def canonical_score(url_path: str, body_size: int, source: str) -> tuple:
    """Higher = better canonical. Sort key descending.

    Source preference: when two captures of the same URL exist, prefer the
    larger body. The final tiebreaker favors the `common-crawl` source
    (older trees are typically frozen; Wayback trees may still grow with
    partial captures during ongoing fetches).
    """
    has_indexphp = url_path.startswith('index.php/') or '/index.php/' in url_path
    is_node = '/node/' in url_path or url_path.startswith('node/')
    is_taxo = '/taxonomy/term/' in url_path
    cc_tiebreak = 1 if source == 'common-crawl' else 0
    return (not has_indexphp, not is_node, not is_taxo, body_size, cc_tiebreak)


def kind_of(url_path: str) -> str:
    if NODE_RE.search(url_path):
        return 'node'
    if TAXO_RE.search(url_path):
        return 'taxonomy'
    return 'page'


# ---------- main ----------

def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    candidates: list[dict] = []
    n_total = 0
    per_source: dict[str, int] = {}
    for source, root in SOURCES:
        if not root.exists():
            print(f'skip missing source: {source} ({root})', file=sys.stderr)
            continue
        print(f'walking {source} tree at {root}...', file=sys.stderr)
        n_src = 0
        for dp, _dn, fns in os.walk(root):
            for fn in fns:
                if not (fn.endswith('.html') or fn.endswith('.htm')):
                    continue
                ap = Path(dp) / fn
                rel = str(ap.relative_to(root))
                url_path = file_to_url_path(rel)
                n_total += 1
                n_src += 1
                title, body = extract(ap)
                if not body:
                    # Skip pages where we couldn't pull any body content
                    continue
                candidates.append({
                    'rel': rel,
                    'source': source,
                    'url_path': url_path,
                    'primary_slug': primary_slug(url_path),
                    'title': title or url_path or '(untitled)',
                    'body_html': body,
                    'body_size': len(body),
                })
                if n_total % 500 == 0:
                    print(f'  ... {n_total} html scanned', file=sys.stderr)
        per_source[source] = n_src

    print(f'  {n_total} html files (by source: {per_source}), '
          f'{len(candidates)} with body', file=sys.stderr)

    # Group by primary slug
    by_slug: dict[str, list[dict]] = {}
    for c in candidates:
        by_slug.setdefault(c['primary_slug'], []).append(c)

    pages: list[dict] = []
    redirects: dict[str, str] = {}
    for slug, cands in by_slug.items():
        cands.sort(
            key=lambda c: canonical_score(c['url_path'], c['body_size'], c['source']),
            reverse=True,
        )
        winner = cands[0]
        # Aliases: every other url_path under this slug, deduped, excluding
        # the canonical path itself.
        seen = {winner['url_path']}
        aliases: list[str] = []
        for c in cands[1:]:
            if c['url_path'] in seen or c['url_path'] == slug:
                continue
            seen.add(c['url_path'])
            aliases.append(c['url_path'])

        # Public output is intentionally minimal: slug + title + body + aliases.
        # Provenance fields (source, node_id, term_id, orig_path, kind) are
        # internal-only and are not emitted into the published JSON.
        rec = {
            'slug': slug or 'index',
            'title': winner['title'],
            'body_html': winner['body_html'],
            'aliases': aliases,
        }
        pages.append(rec)
        for a in aliases:
            # Map every alias path to the canonical slug path
            redirects[f'/{a}'] = f'/{slug}' if slug else '/'

    # Sort pages alphabetically for deterministic output
    pages.sort(key=lambda p: p['slug'])

    pages_path = DATA_DIR / 'pages.json'
    redirects_path = DATA_DIR / 'redirects.json'
    pages_path.write_text(json.dumps(pages, ensure_ascii=False))
    redirects_path.write_text(json.dumps(redirects, sort_keys=True, indent=0))

    # Summary (winner-internal counts derived from the candidate list, not the
    # public rec — we deliberately don't ship source/kind in pages.json).
    n_pages = len(pages)
    n_aliases = sum(len(p['aliases']) for p in pages)
    winner_by_source: dict[str, int] = {}
    for slug, cands in by_slug.items():
        winner = max(cands, key=lambda c: canonical_score(c['url_path'], c['body_size'], c['source']))
        winner_by_source[winner['source']] = winner_by_source.get(winner['source'], 0) + 1
    print(f'\nimport done', file=sys.stderr)
    print(f'  canonical pages : {n_pages}', file=sys.stderr)
    print(f'  alias redirects : {n_aliases}', file=sys.stderr)
    print(f'  by source       : {winner_by_source}', file=sys.stderr)
    print(f'  → {pages_path}', file=sys.stderr)
    print(f'  → {redirects_path}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
