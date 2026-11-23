/* Merge account certificates into the existing browser cart, without a reload after Add. */
(function () {
  'use strict';
  const LAST = 'sports-cave:last-storefront-page';
  const POSITION = LAST + ':position';
  const PENDING = 'sports-cave:certificate-cart-pending';
  const endpoint = 'https://sports-cave-image-factory.onrender.com/api/collector-vault/frame/cart-handoff';
  function targetPath(value, origin) {
    try {
      const url = new URL(value || '/collections/all-sports-wall-art', origin);
      if (url.origin !== origin || /\/(account|cart|checkout|checkouts)(\/|$)/.test(url.pathname)) return '/collections/all-sports-wall-art?sc_cart=1';
      url.searchParams.delete('sc_certificate_cart');
      url.searchParams.set('sc_cart', '1');
      return url.pathname + url.search + url.hash;
    } catch (_) { return '/collections/all-sports-wall-art?sc_cart=1'; }
  }
  async function readJson(fetcher, url, options = {}) {
    const response = await fetcher(url, {...options, signal: AbortSignal.timeout(20000)});
    const body = await response.json();
    if (!response.ok) throw new Error(body.description || 'Certificate cart is temporarily unavailable.');
    return body;
  }
  function contains(cart, item) {
    return (cart.items || []).some(line => String(line.variant_id || line.id) === String(item.variant_id)
      && line.properties?._sports_cave_frame_request === item.request_reference && line.quantity > 0);
  }
  async function transfer(token, env) {
    const root = env.root || '/';
    const [item, cart] = await Promise.all([
      readJson(env.fetch, endpoint, {method: 'POST', credentials: 'omit', cache: 'no-store',
        referrerPolicy: 'no-referrer', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({token})}),
      readJson(env.fetch, root + 'cart.js', {credentials: 'same-origin', cache: 'no-store'})
    ]);
    if (!item.ok || !/^\d+$/.test(String(item.variant_id)) || !item.request_reference
        || item.properties?._sports_cave_frame_request !== item.request_reference) throw new Error('Certificate handoff unavailable. Return to My Collection and try again.');
    env.onItem?.(item);
    let sections;
    if (!contains(cart, item)) {
      let added;
      try {
        added = await readJson(env.fetch, root + 'cart/add.js', {method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
            items: [{id: Number(item.variant_id), quantity: 1, properties: item.properties}],
            ...(env.sections?.length ? {sections: env.sections, sections_url: env.path || root} : {})
          })});
      } catch (error) {
        // A timed-out POST may have succeeded. Reconcile before offering a retry.
        const confirmed = await readJson(env.fetch, root + 'cart.js', {credentials: 'same-origin', cache: 'no-store'});
        if (!contains(confirmed, item)) throw error;
      }
      sections = added?.sections;
    }
    if (env.sections?.some(id => !sections?.[id])) {
      sections = await readJson(env.fetch, root + '?sections=' + encodeURIComponent(env.sections.join(',')),
        {credentials: 'same-origin', cache: 'no-store'});
    }
    await env.onCart?.({item, sections});
    return item.destination === 'checkout' ? root + 'checkout' : targetPath(env.lastPage, env.origin);
  }
  if (typeof module !== 'undefined' && module.exports) { module.exports = {transfer, targetPath}; return; }
  if (window.scCertificateCartBridge) return;
  window.scCertificateCartBridge = true;
  const url = new URL(location.href);
  let token = url.searchParams.get('sc_certificate_cart');
  if (!token) {
    try { const pending = JSON.parse(sessionStorage.getItem(PENDING)); if (pending?.expires > Date.now()) token = pending.token; } catch (_) {}
  }
  if (!token) {
    const remember = () => {
      const current = new URL(location.href);
      if (/\/(account|cart|checkout|checkouts)(\/|$)/.test(current.pathname)) return;
      current.searchParams.delete('sc_cart');
      try {
        const path = current.pathname + current.search + current.hash;
        localStorage.setItem(LAST, path);
        localStorage.setItem(POSITION, JSON.stringify({path, y: scrollY}));
      } catch (_) {}
    };
    remember();
    addEventListener('pagehide', remember);
    document.addEventListener('click', event => {
      const link = event.target.closest?.('a[href]');
      if (link && /^(account\.)?sportscaveshop\.com$/.test(new URL(link.href).hostname)) remember();
    }, {capture: true});
    return;
  }
  let lastPage;
  try { lastPage = localStorage.getItem(LAST); } catch (_) {}
  const target = new URL(targetPath(lastPage, location.origin), location.origin);
  const here = new URL(location.href);
  ['sc_certificate_cart', 'sc_cart', 'country', 'sso'].forEach(key => { here.searchParams.delete(key); });
  const destination = new URL(target);
  ['sc_cart', 'country', 'sso'].forEach(key => { destination.searchParams.delete(key); });
  if (here.pathname + here.search !== destination.pathname + destination.search) {
    target.searchParams.set('sc_certificate_cart', token);
    const country = url.searchParams.get('country');
    if (country) target.searchParams.set('country', country);
    location.replace(target.pathname + target.search + target.hash);
    return;
  }
  try { sessionStorage.setItem(PENDING, JSON.stringify({token, expires: Date.now() + 30 * 60000})); } catch (_) {}
  url.searchParams.delete('sc_certificate_cart');
  url.searchParams.delete('sc_cart');
  history.replaceState(history.state, '', url.pathname + url.search + url.hash);
  const uiReady = async () => {
    if (document.readyState === 'loading') await new Promise(resolve => document.addEventListener('DOMContentLoaded', resolve, {once: true}));
    if (!document.querySelector('cart-drawer')) throw new Error('Cart drawer unavailable');
    await customElements.whenDefined('cart-drawer');
  };
  async function run() {
    await uiReady();
    const drawer = document.querySelector('cart-drawer');
    try {
      const position = JSON.parse(localStorage.getItem(POSITION));
      const current = new URL(location.href); current.searchParams.delete('country'); current.searchParams.delete('sso');
      if (position?.path === current.pathname + current.search + current.hash) scrollTo(0, Number(position.y) || 0);
    } catch (_) {}
    drawer.open(null);
    const form = drawer.querySelector('cart-form');
    form?.setAttribute('aria-busy', 'true');
    if (form) form.inert = true;
    const notice = document.createElement('div');
    notice.setAttribute('role', 'status');
    notice.style.cssText = 'padding:12px 20px;color:inherit';
    notice.textContent = 'Adding your framed certificate…';
    drawer.prepend(notice);
    const targets = ['page-header', 'cart-drawer'].map(selector => document.querySelector(selector)).filter(el => el?.dataset.sectionId);
    const work = () => transfer(token, {
      fetch: window.fetch.bind(window), root: window.Shopify?.routes?.root || '/', origin: location.origin,
      lastPage, path: location.pathname, sections: targets.map(el => el.dataset.sectionId),
      onItem(item) {
        const preview = item.properties._sports_cave_certificate_preview;
        if (preview?.startsWith('https://sports-cave-image-factory.onrender.com/api/collector-vault/frame/preview?')) {
          const image = new Image(); image.src = preview;
        }
      },
      async onCart({item, sections}) {
        if (!sections || targets.some(el => !sections[el.dataset.sectionId])) throw new Error('Cart display unavailable');
        targets.forEach(el => {
          if (typeof el.updateFromCartChange === 'function') el.updateFromCartChange(sections[el.dataset.sectionId]);
        });
        document.dispatchEvent(new CustomEvent('on:cart:add', {bubbles: true, detail: {variantId: Number(item.variant_id)}}));
      }
    });
    try {
      const path = navigator.locks ? await navigator.locks.request('sc-certificate-cart', work) : await work();
      try { sessionStorage.removeItem(PENDING); } catch (_) {}
      notice.textContent = 'Your framed certificate is in your cart.';
      if (path.endsWith('/checkout')) location.assign(path);
    } catch (error) {
      notice.setAttribute('role', 'alert');
      notice.textContent = 'Your certificate could not be added. Please try again. ';
      const retry = document.createElement('button');
      retry.type = 'button'; retry.className = 'btn'; retry.textContent = 'Try again';
      retry.addEventListener('click', () => { notice.remove(); run().catch(showFallback); }, {once: true});
      notice.append(retry);
    } finally {
      form?.removeAttribute('aria-busy');
      if (form) form.inert = false;
    }
  }
  function showFallback() {
    const notice = document.createElement('p'); notice.setAttribute('role', 'alert');
    notice.textContent = 'Your framed certificate could not be added. Return to My Collection and try again.';
    (document.querySelector('main') || document.body).prepend(notice);
  }
  run().catch(showFallback);
}());
