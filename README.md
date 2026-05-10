# itfc-astro

Static reconstruction of the IT for Change website (itforchange.net), built
with [Astro 6](https://astro.build) and deployed to GitHub Pages.

## Stack

- **Astro 6** static site generator
- **Tailwind v4** + **Typography plugin** for prose
- **TypeScript 6** strict mode (`astro check` runs in CI)
- **`@astrojs/sitemap`** for the XML sitemap; in-page A–Z sitemap at `/sitemap`
- **Bun 1.3** for install + scripts

## Project layout

```
src/
  pages/            route files (index, [...slug], sitemap, ...)
  layouts/          page chrome
  components/       header, footer, nav
  data/             pages.json (content corpus), redirects.json (alias→canonical)
  lib/              with-base helper for portable BASE_URL rewriting
  styles/           global.css (theme tokens + Tailwind)
public/             static assets served at site root
scripts/            content import pipeline (Python)
```

## Local development

```sh
bun install
bun run dev          # localhost:4321
bun run check        # TypeScript / Astro strict checks
bun run build        # → ./dist
```

## Deploy

CI builds on push to `main` and publishes to GitHub Pages.
`SITE_URL` and `BASE_PATH` are resolved automatically by
`actions/configure-pages`, so the same code base flips cleanly from the
`<user>.github.io/<repo>/` URL to a custom domain (drop a `CNAME` file
in `public/` when ready).

## Refreshing content

```sh
bun run import       # rebuilds src/data/{pages.json,redirects.json}
```

## License

Site content © IT for Change, licensed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
Code in this repository is released under the MIT License (see `LICENSE`).
