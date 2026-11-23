// Country context is passed to both price reads and cart writes.
export function accountCountry(api) {
  const signal = api?.localization?.country;
  const value = signal?.value ?? signal?.current;
  return /^[A-Z]{2}$/.test(value?.isoCode || '') ? value.isoCode : 'AU';
}
export function compactTitle(title) {
  return String(title || '').replace(/\bwall\s+art\b/gi, '').replace(/\s+/g, ' ').replace(/\s+[–—-]\s*$/, '').trim();
}
export function pairedProducts(ids, nodes) {
  const byId = new Map((nodes || []).filter(Boolean).map(product => [product.id, product]));
  return [...new Set(ids)].map(id => byId.get(id))
    .filter(product => product?.handle && product.variants?.nodes?.some(variant => variant.availableForSale))
    .slice(0, 2);
}
export function comparePrice(variant) {
  const price=variant?.price, compare=variant?.compareAtPrice;
  return price && compare && price.currencyCode===compare.currencyCode && Number(compare.amount)>Number(price.amount) ? compare : null;
}
export const UPSELL_QUERY = `query CollectionUpsellVariants($ids: [ID!]!, $country: CountryCode!) @inContext(country: $country) {
  nodes(ids: $ids) { ... on Product { id title handle featuredImage { url altText }
    variants(first: 100) { nodes { id title availableForSale selectedOptions { name value }
      price { amount currencyCode } compareAtPrice { amount currencyCode } image { url altText } } }
  } }
}`;
export const FRAME_PRICE_QUERY = `query AccountCertificatePrices($id: ID!, $country: CountryCode!) @inContext(country: $country) {
  product(id: $id) { id variants(first: 20) { nodes { id availableForSale price { amount currencyCode } } } }
}`;
export function marketFrames(product, data) {
  if (!data || data.id!==product.product_id) throw new Error('Frame prices unavailable');
  const priced = (product.variants || []).flatMap(variant => {
    const current=data.variants.nodes.find(v=>v.id===variant.variant_id && v.availableForSale);
    return current ? [{...variant,contextual_price:current.price}] : [];
  });
  if (!priced.length) throw new Error('No available frame for this country');
  return {...product,variants:priced,variant_id:priced[0].variant_id,contextual_price:priced[0].contextual_price};
}
