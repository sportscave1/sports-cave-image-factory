// Fetch only the first two ordered product images; Shopify CDN delivers a small preview.
export const REVIEW_IMAGE_QUERY = `query CollectionReviewImage($id: ID!) {
  product(id: $id) { images(first: 2) { nodes { url(transform: {maxWidth: 640}) altText } } }
}`;

export function reviewProductId(prompt, certificate) {
  return prompt?.shopify_product_id || certificate?.shopify_product_id || "";
}

export function secondProductImage(product) {
  const image = product?.images?.nodes?.[1];
  if (!image?.url) return null;
  try { if (new URL(image.url).protocol !== "https:") return null; } catch { return null; }
  return image;
}
