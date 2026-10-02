// Small allowlisted Shopify app-pixel events; no email/name/address/URL payloads.
export const EVENTS = ['product_viewed', 'product_added_to_cart', 'product_removed_from_cart', 'cart_viewed', 'checkout_started', 'checkout_completed'];

export function start({analytics, init, customerPrivacy, settings}, transport = fetch) {
  let privacy = init.customerPrivacy;
  if (!/^https:\/\/[^/]+\/shopify\/customer-events$/.test(settings.endpoint || '')) return;
  customerPrivacy.subscribe('visitorConsentCollected', event => { privacy = event.customerPrivacy; });
  for (const name of EVENTS) analytics.subscribe(name, event => {
    if (!privacy?.analyticsProcessingAllowed || !privacy?.marketingAllowed) return;
    const variant = event.data?.productVariant || event.data?.cartLine?.merchandise;
    const id = variant?.product?.id;
    const product = /^gid:\/\/shopify\/Product\/\d+$/.test(id || '') ? id : /^\d+$/.test(String(id || '')) ? `gid://shopify/Product/${id}` : '';
    const payload = {
      event_id: event.id, event_name: name, client_id: event.clientId,
      product_id: product, occurred_at: event.timestamp,
      shop: settings.shop, ingestionId: settings.ingestionId,
      analytics_allowed: true, marketing_allowed: true,
    };
    Promise.resolve(transport(settings.endpoint, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload), keepalive: true})).catch(() => {});
  });
}
