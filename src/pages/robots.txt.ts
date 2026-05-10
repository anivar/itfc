import type { APIRoute } from 'astro';

// Generated robots.txt — open to indexers (this is a public archival mirror
// of itforchange.net) and points crawlers at the @astrojs/sitemap output.
//
// SITE_URL + BASE_PATH come from astro.config.mjs (env-driven by the GH Pages
// configure-pages step), so the sitemap URL resolves to the deployed origin
// — github.io subpath in CI, local origin in dev — without code changes.
export const GET: APIRoute = ({ site }) => {
  // `site` is the origin (no base) per astro.config; BASE_URL has the
  // configured /<base>/ prefix. Combine them so the sitemap link points
  // at the actual deployed location even on the gh.io subpath.
  const sitemap = site
    ? new URL(`${import.meta.env.BASE_URL}sitemap-index.xml`.replace(/\/+/g, '/'), site).toString()
    : '/sitemap-index.xml';
  const body = [
    'User-agent: *',
    'Allow: /',
    '',
    `Sitemap: ${sitemap}`,
    '',
  ].join('\n');
  return new Response(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
