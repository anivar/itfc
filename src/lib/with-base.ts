// Rewrite root-relative URLs in HTML so the same content payload renders
// correctly under any deploy base (e.g. "/itfc/" on the showcase, "/" on
// the production domain). Only attributes whose values start with "/" are
// touched; absolute and protocol-relative URLs are left untouched.

const BASE = (import.meta.env.BASE_URL || '/').replace(/\/+$/, '') + '/';

// Prefix a single root-relative path with the build BASE_URL. Use in Astro
// component templates wherever a static internal link is hard-coded
// (e.g. `<a href={bp('/aboutus')}>` ).
export function bp(path: string): string {
  if (!path) return BASE;
  if (path.startsWith('//') || /^[a-z]+:/i.test(path)) return path;
  if (!path.startsWith('/')) return path;
  return BASE + path.replace(/^\/+/, '');
}

const ATTR_RE = /\b(href|src|srcset|poster|data-src|action)\s*=\s*("|')(\/[^"'\s>]*)("|')/gi;

function rewriteOne(path: string): string {
  // Skip protocol-relative ("//host/x") and the "/" root itself collapses to BASE.
  if (path.startsWith('//')) return path;
  return BASE + path.replace(/^\/+/, '');
}

function rewriteSrcset(value: string): string {
  return value
    .split(',')
    .map((part) => {
      const m = part.trim().match(/^(\S+)(\s+\S+)?$/);
      if (!m) return part;
      const url = m[1];
      const descriptor = m[2] ?? '';
      if (!url.startsWith('/') || url.startsWith('//')) return part;
      return rewriteOne(url) + descriptor;
    })
    .join(', ');
}

export function withBase(html: string): string {
  if (BASE === '/') return html;
  return html.replace(ATTR_RE, (_m, attr: string, q1: string, val: string, q2: string) => {
    const rewritten = attr.toLowerCase() === 'srcset' ? rewriteSrcset(val) : rewriteOne(val);
    return `${attr}=${q1}${rewritten}${q2}`;
  });
}
