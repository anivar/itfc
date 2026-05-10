// Loads all page entries from the sharded JSON files under
// src/data/pages/. Splitting keeps each file under GitHub's 50 MB
// warning threshold while letting the build read every page eagerly
// (Astro static output materialises one HTML file per slug).
//
// Vite resolves the glob at build time and the JSON files become tree
// entries baked into the bundle — there is no runtime fetch.

export type Page = {
  slug: string;
  title: string;
  body_html: string;
  aliases?: string[];
};

const modules = import.meta.glob<{ default: Page[] }>(
  '../data/pages/*.json',
  { eager: true },
);

const pages: Page[] = Object.keys(modules)
  .sort()
  .flatMap((k) => modules[k].default);

export default pages;
