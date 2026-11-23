// UI thumbnails only. Never apply this to a certificate or printable download.
export function collectionThumbnail(value, width = 320) {
  if (!value) return "";
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.hostname !== "cdn.shopify.com" || !url.pathname.startsWith("/s/files/")) return value;
    if ([...url.searchParams.keys()].some(key => /^(token|signature|hmac|x-amz-signature)$/i.test(key))) return value;
    if (!Number.isInteger(width) || width < 1 || width > 1200) return value;
    const existing = Number(url.searchParams.get("width"));
    // Keep an existing smaller thumbnail; do not upscale it.
    url.searchParams.set("width", String(existing > 0 ? Math.min(existing, width) : width));
    return url.href;
  } catch { return value; }
}
