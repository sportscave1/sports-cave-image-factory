/* Shopify Settings > Customer events > Custom pixel. Do not install/enable without approval.
 * Require Analytics AND Marketing permission in the Shopify pixel settings.
 * Generated disabled; test_context remains true for installation verification.
 * Uses only supported pixel snapshot, privacy, analytics and browser storage APIs.
 */
(function () {
  const config = __SC_CONFIG__;
  if (!config.enabled) return;
  const privacyApi = typeof customerPrivacy !== 'undefined' ? customerPrivacy : api.customerPrivacy;
  let consent = init.customerPrivacy || {};
  let session = null;
  let generation = 0;
  const allowed = () => consent.analyticsProcessingAllowed === true && consent.marketingAllowed === true;
  const storageKey = 'sports_cave_campaign_context_v1';
  privacyApi.subscribe('visitorConsentCollected', event => {
    consent = event.customerPrivacy || {};
    generation += 1;
    if (!allowed()) { session = null; browser.sessionStorage.removeItem(storageKey).catch(() => {}); }
  });
  const events = ['page_viewed', 'product_viewed', 'product_added_to_cart', 'checkout_started', 'checkout_completed'];
  for (const name of events) analytics.subscribe(name, async event => {
    if (!allowed()) return;
    const current = generation;
    try {
      let context = {};
      const url = new URL(event.context.document.location.href);
      const key = url.searchParams.get('utm_campaign') || '';
      if (url.searchParams.get('utm_source') === 'sports_cave' && url.searchParams.get('utm_medium') === 'email' && /^sc_[a-f0-9]{32}$/.test(key)) {
        context = { campaign: key, test: url.searchParams.get('sc_test') === '1' };
        if (!allowed() || current !== generation) return;
        await browser.sessionStorage.setItem(storageKey, JSON.stringify(context));
      } else {
        try { context = JSON.parse(await browser.sessionStorage.getItem(storageKey) || '{}'); } catch (_) { context = {}; }
      }
      if (!allowed() || current !== generation) return;
      if (!session) session = crypto.randomUUID();
      const data = event.data || {};
      const product = data.productVariant?.product?.id || data.cartLine?.merchandise?.product?.id || '';
      const payload = {
        pixel_id: config.pixel_id, event_id: event.id, event_type: name, session_ref: session,
        campaign_key: /^sc_[a-f0-9]{32}$/.test(context.campaign || '') ? context.campaign : '',
        product_ref: /^gid:\/\/shopify\/Product\/\d+$/.test(product) ? product : '',
        occurred_at: event.timestamp, test_context: config.test_context || context.test === true,
        analytics_allowed: true, marketing_allowed: true
      };
      if (!allowed() || current !== generation) return;
      await fetch(config.endpoint, { method: 'POST', headers: {'Content-Type': 'application/json'},
        mode: 'cors', credentials: 'omit', keepalive: true, body: JSON.stringify(payload) });
    } catch (_) { /* Fail closed; do not log customer snapshots or retry events. */ }
  });
})();
