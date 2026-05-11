// @ts-check
//
// itfc-astro build config.
// Pattern lifted from anivar/rethink-aadhaar — env-driven SITE/BASE for GH
// Pages, alias→canonical 302 redirects baked at build, sitemap integration.

import { existsSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

const SITE = process.env.SITE_URL ?? 'http://localhost:4321';
const BASE = process.env.BASE_PATH ?? '/';

// Pull alias→canonical map produced by scripts/import_cc_content.py.
// 302 (temporary) so the move to the official domain later doesn't get
// cached too aggressively.
const redirectsFile = fileURLToPath(new URL('./src/data/redirects.json', import.meta.url));
const publicDir = fileURLToPath(new URL('./public', import.meta.url));
/** @type {Record<string, { status: 302; destination: string }>} */
let redirects = {};
if (existsSync(redirectsFile)) {
  /** @type {Record<string, string>} */
  const raw = JSON.parse(readFileSync(redirectsFile, 'utf8'));
  // Drop any FROM that resolves to a real static file in public/. Astro
  // would otherwise try to mkdir <from>/index.html for the meta-refresh
  // stub and ENOTDIR on the existing file (e.g. wayback PDFs under
  // /sites/default/files/). Direct file serving is the right behavior anyway.
  /** @param {string} from */
  const collidesWithStatic = (from) => {
    const rel = from.startsWith('/') ? from.slice(1) : from;
    try { return statSync(`${publicDir}/${rel}`).isFile(); } catch { return false; }
  };
  redirects = Object.fromEntries(
    Object.entries(raw)
      .filter(([from]) => !collidesWithStatic(from))
      .map(([from, to]) => [from, { status: 302, destination: to }]),
  );
}

export default defineConfig({
  site: SITE,
  base: BASE,
  output: 'static',
  trailingSlash: 'ignore',
  build: { format: 'directory' },
  redirects,
  integrations: [
    sitemap({
      changefreq: 'monthly',
      priority: 0.5,
      // Drop internal redirect endpoints + Drupal listing query-string artifacts.
      filter: (page) => !page.includes('/index.php/') && !/[?&=]|%3F/i.test(page),
      serialize(item) {
        const u = new URL(item.url);
        // BASE may be `/itfc/` on GH Pages or `/` on a custom domain;
        // strip the prefix before matching so the home + section bumps
        // apply on both deploys.
        const base = (BASE.endsWith('/') ? BASE : `${BASE}/`).replace(/\/+$/, '');
        const p = u.pathname.replace(new RegExp(`^${base}`), '').replace(/\/$/, '');
        if (p === '') item.priority = 1.0;
        else if (
          ['/aboutus', '/focus-areas', '/research', '/resources_all', '/sitemap'].includes(p)
        )
          item.priority = 0.9;
        return item;
      },
    }),
  ],
  vite: {
    plugins: [tailwindcss()],
    server: {
      fs: { allow: ['..', '/home/niyam/itfc'] },
    },
  },
});
