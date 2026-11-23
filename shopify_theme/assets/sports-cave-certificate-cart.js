/* Certificate-only handoff into the existing browser cart and Symmetry drawer. */
(function () {
  'use strict';
  const LAST = 'sports-cave:last-storefront-page';
  const endpoint = 'https://sports-cave-image-factory.onrender.com/api/collector-vault/frame/cart-handoff';
  function targetPath(value, origin) {
    try {
      const url = new URL(value || '/collections/all-sports-wall-art', origin);
      if (url.origin !== origin || /^\/(account|cart|checkout|checkouts)(\/|$)/.test(url.pathname)) return '/collections/all-sports-wall-art?sc_cart=1';
      url.searchParams.delete('sc_certificate_cart');
      url.searchParams.set('sc_cart', '1');
      return url.pathname + url.search;
    } catch (_) { return '/collections/all-sports-wall-art?sc_cart=1'; }
  }
  async function transfer(token, env) {
    const answer = await env.fetch(endpoint, {method: 'POST', credentials: 'omit', cache: 'no-store',
      referrerPolicy: 'no-referrer', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token})});
    const item = await answer.json();
    if (!answer.ok || !item.ok || !/^\d+$/.test(String(item.variant_id)) || !item.request_reference) throw new Error('Certificate handoff unavailable');
    const root = env.root || '/';
    const response = await env.fetch(root + 'cart.js', {credentials: 'same-origin', cache: 'no-store'});
    if (!response.ok) throw new Error('Cart unavailable');
    const cart = await response.json();
    const found = (cart.items || []).some(line => String(line.variant_id || line.id) === String(item.variant_id)
      && line.properties?._sports_cave_frame_request === item.request_reference && line.quantity > 0);
    if (!found) {
      const added = await env.fetch(root + 'cart/add.js', {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({items: [{id: Number(item.variant_id), quantity: 1, properties: item.properties}]})});
      if (!added.ok) throw new Error('Certificate could not be added');
    }
    // Preserve every existing product. Never replace/clear the browser cart.
    return targetPath(env.lastPage, env.origin);
  }
  if (typeof module !== 'undefined' && module.exports) { module.exports = {transfer, targetPath}; return; }
  const url = new URL(location.href);
  const token = url.searchParams.get('sc_certificate_cart');
  if (!token) {
    if (!/^\/(account|cart|checkout|checkouts)(\/|$)/.test(url.pathname)) {
      url.searchParams.delete('sc_cart');
      try { localStorage.setItem(LAST, url.pathname + url.search); } catch (_) {}
    }
    return;
  }
  url.searchParams.delete('sc_certificate_cart');
  history.replaceState(history.state, '', url.pathname + url.search + url.hash);
  let lastPage;
  try { lastPage = localStorage.getItem(LAST); } catch (_) {}
  transfer(token, {fetch: window.fetch.bind(window), root: window.Shopify?.routes?.root || '/', lastPage, origin: location.origin})
    .then(path => location.replace(path))
    .catch(() => {
      const notice = document.createElement('p');
      notice.setAttribute('role', 'alert');
      notice.textContent = 'Your framed certificate could not be added. Return to My Collection and try Checkout now again.';
      (document.querySelector('main') || document.body).prepend(notice);
    });
}());
