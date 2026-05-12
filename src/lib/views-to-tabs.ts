/**
 * Wrap the two Drupal view-display blocks on a landing page (e.g. /networks
 * and /events) into a CSS-only tab UI.
 *
 * The original site rendered two `view-display-id-block_1` and `block_2`
 * sibling blocks under "Networks initiated by us" / "Networks we are part of"
 * (or "PAST EVENTS" / "UPCOMING EVENTS") as a switchable tab pair. The
 * Wayback-captured HTML lost the tab JS so they stack vertically. This
 * helper reconstructs the tabs at build time using radio-button +
 * sibling-selector CSS so no client JS is needed.
 *
 * Structure we're looking for in the body_html:
 *
 *   <section class="…block-views block-views-block{view}-page-view-block-1…">
 *     <h2 class="block-title">LABEL_1</h2>
 *     …view-display-id-block_1…
 *   </section>
 *   <section class="…block-views block-views-block{view}-page-view-block-2…">
 *     <h2 class="block-title">LABEL_2</h2>
 *     …view-display-id-block_2…
 *   </section>
 */

const BLOCK_OPEN_RE =
  /<section\s+class="[^"]*\bblock-views\s+block-views-block[a-z_-]+-page-view-block-(1|2)\b[^"]*"[^>]*>/gi;

/**
 * Find the closing `</section>` for a section opening at `openIdx`, handling
 * any nested `<section>` tags by depth counting.
 */
function findSectionEnd(body: string, openIdx: number): number {
  const openTag = /<section\b[^>]*>/gi;
  const closeTag = /<\/section>/gi;
  let depth = 1;
  let i = body.indexOf('>', openIdx) + 1;
  while (depth > 0 && i < body.length) {
    openTag.lastIndex = i;
    closeTag.lastIndex = i;
    const o = openTag.exec(body);
    const c = closeTag.exec(body);
    if (!c) return -1;
    if (o && o.index < c.index) {
      depth++;
      i = o.index + o[0].length;
    } else {
      depth--;
      i = c.index + c[0].length;
    }
  }
  return i;
}

export function tabifyTwoViewBlocks(body: string, opts?: { idPrefix?: string }): string {
  if (!body) return body;
  if (body.includes('class="itfc-tabs"')) return body; // already wrapped (idempotent)

  // Find the two block-views sections (block-1 and block-2 of the same view).
  let block1: { start: number; end: number; idx: number } | null = null;
  let block2: { start: number; end: number; idx: number } | null = null;
  let m: RegExpExecArray | null;
  BLOCK_OPEN_RE.lastIndex = 0;
  while ((m = BLOCK_OPEN_RE.exec(body)) !== null) {
    const which = m[1];
    const end = findSectionEnd(body, m.index);
    if (end < 0) continue;
    if (which === '1' && !block1) {
      block1 = { start: m.index, end, idx: 1 };
    } else if (which === '2' && !block2) {
      block2 = { start: m.index, end, idx: 2 };
    }
    if (block1 && block2) break;
  }
  if (!block1 || !block2) return body;

  const seg1 = body.slice(block1.start, block1.end);
  const seg2 = body.slice(block2.start, block2.end);

  // Extract the H2 label inside each section to use as the tab label.
  const labelRe = /<h2\s+class="block-title">([^<]+)<\/h2>/i;
  const l1 = seg1.match(labelRe);
  const l2 = seg2.match(labelRe);
  if (!l1 || !l2) return body;
  const label1 = l1[1].trim();
  const label2 = l2[1].trim();

  // Strip the duplicate H2 from inside the panel — the tab label above
  // already names the section.
  const stripH2 = (h: string) => h.replace(labelRe, '');
  const panel1 = stripH2(seg1);
  const panel2 = stripH2(seg2);

  const idPrefix = opts?.idPrefix || 'tabs';
  const tabBlock = `
<div class="itfc-tabs" data-itfc-tabs>
  <input type="radio" name="${idPrefix}" id="${idPrefix}-1" class="itfc-tab-input" checked>
  <input type="radio" name="${idPrefix}" id="${idPrefix}-2" class="itfc-tab-input">
  <div class="itfc-tab-list" role="tablist">
    <label for="${idPrefix}-1" class="itfc-tab" role="tab" id="${idPrefix}-tab-1">${label1}</label>
    <label for="${idPrefix}-2" class="itfc-tab" role="tab" id="${idPrefix}-tab-2">${label2}</label>
  </div>
  <div class="itfc-tab-panels">
    <section class="itfc-tab-panel itfc-tab-panel-1" role="tabpanel" aria-labelledby="${idPrefix}-tab-1">
      ${panel1}
    </section>
    <section class="itfc-tab-panel itfc-tab-panel-2" role="tabpanel" aria-labelledby="${idPrefix}-tab-2">
      ${panel2}
    </section>
  </div>
</div>
`;

  // Replace the entire range from start of block1 through end of block2 with
  // the tab block. (Any whitespace between block1 and block2 is intentionally
  // dropped — it would have been pure inter-section padding.)
  return body.slice(0, block1.start) + tabBlock + body.slice(block2.end);
}
