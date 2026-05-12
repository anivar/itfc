/**
 * Add `loading="lazy"` and `decoding="async"` to every `<img>` tag in a
 * body HTML string that doesn't already have those attributes.
 *
 * Some legacy landings (notably /events with 519 images and /networks with
 * 24) ship a single large body_html blob with every list item inline.
 * Without lazy-loading the browser fetches every image as a render-blocking
 * subresource, delaying first paint of the page header and tab UI. The
 * images all have intrinsic width/height from the Drupal `img-responsive`
 * markup so there's no CLS cost.
 */

const IMG_TAG_RE = /<img\b([^>]*?)(\/?)>/gi;
const HAS_LOADING_RE = /\bloading\s*=/i;
const HAS_DECODING_RE = /\bdecoding\s*=/i;

export function lazifyImages(html: string): string {
  if (!html) return html;
  return html.replace(IMG_TAG_RE, (full, attrs: string, selfClose: string) => {
    const addLoading = !HAS_LOADING_RE.test(attrs);
    const addDecoding = !HAS_DECODING_RE.test(attrs);
    if (!addLoading && !addDecoding) return full;
    const extras =
      (addLoading ? ' loading="lazy"' : '') +
      (addDecoding ? ' decoding="async"' : '');
    return `<img${attrs}${extras}${selfClose ? ' /' : ''}>`;
  });
}
