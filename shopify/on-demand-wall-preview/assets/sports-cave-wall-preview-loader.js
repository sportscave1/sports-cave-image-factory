(function () {
  'use strict';
  if (window.__scLightPreviewLoader) return;
  window.__scLightPreviewLoader = true;
  const assets = new Map();
  const pendingRoots = new WeakMap();
  let active = null;

  function loadAsset(url, stylesheet) {
    if (!url) return Promise.reject(new Error('Missing preview asset'));
    if (!assets.has(url)) {
      const pending = new Promise(function (resolve, reject) {
        const node = document.createElement(stylesheet ? 'link' : 'script');
        const timer = setTimeout(function () { fail(); }, 20000);
        function fail() {
          clearTimeout(timer);
          node.remove();
          reject(new Error('Preview asset unavailable'));
        }
        if (stylesheet) { node.rel = 'stylesheet'; node.href = url; }
        else { node.src = url; }
        node.onload = function () { clearTimeout(timer); resolve(); };
        node.onerror = fail;
        document.head.append(node);
      }).catch(function (error) { assets.delete(url); throw error; });
      assets.set(url, pending);
    }
    return assets.get(url);
  }

  async function hydrate(root) {
    if (root.querySelector('[data-sc-wall-overlay]')) return;
    const url = new URL(location.href);
    url.searchParams.delete('sections');
    url.searchParams.set('section_id', 'sc-wall-preview');
    const controller = new AbortController();
    const timer = setTimeout(function () { controller.abort(); }, 20000);
    try {
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) throw new Error('Preview unavailable');
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      const content = doc.querySelector('[data-sc-wall-root]');
      if (!content?.querySelector('[data-sc-wall-overlay]') || content.dataset.productId !== root.dataset.productId) throw new Error('Preview unavailable');
      for (const attr of content.attributes) root.setAttribute(attr.name, attr.value);
      root.replaceChildren(...Array.from(content.childNodes));
    } finally { clearTimeout(timer); }
  }

  function prepare(root) {
    if (root.scWallOpen) return Promise.resolve();
    if (!pendingRoots.has(root)) {
      const work = Promise.allSettled([
        hydrate(root),
        loadAsset(root.dataset.scWallCss, true),
        loadAsset(root.dataset.scWallArtwork, false)
      ]).then(function (results) {
        const failure = results.find(function (result) { return result.status === 'rejected'; });
        if (failure) throw failure.reason;
        return loadAsset(root.dataset.scWallJs, false);
      }).then(function () {
        document.dispatchEvent(new CustomEvent('sc:wall-preview:hydrate', { detail: { root: root } }));
        if (typeof root.scWallOpen !== 'function') throw new Error('Preview unavailable');
      }).finally(function () { pendingRoots.delete(root); });
      pendingRoots.set(root, work);
    }
    return pendingRoots.get(root);
  }

  function loadingDialog(trigger, root) {
    const dialog = document.createElement('dialog');
    dialog.setAttribute('aria-label', 'Your wall preview');
    dialog.setAttribute('data-sc-wall-loading-dialog', '');
    dialog.style.cssText = 'position:fixed;inset:0;margin:auto;width:min(420px,calc(100vw - 32px));box-sizing:border-box;padding:28px;background:#121212;color:#f7f5ef;border:1px solid #D4A54C;border-radius:12px;font:inherit;z-index:2147483647';
    const title = document.createElement('strong');
    title.textContent = 'SPORTS CAVE';
    title.style.cssText = 'color:#D4A54C;letter-spacing:.12em;font-size:12px';
    const status = document.createElement('p');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    const retry = document.createElement('button');
    retry.type = 'button'; retry.textContent = 'Try again'; retry.hidden = true;
    const close = document.createElement('button');
    close.type = 'button'; close.textContent = 'Close';
    for (const button of [retry, close]) button.style.cssText = 'padding:10px 18px;margin:6px 8px 0 0;background:#121212;color:#f7f5ef;border:1px solid #D4A54C;border-radius:5px;font:inherit;cursor:pointer';
    dialog.append(title, status, retry, close);
    document.body.append(dialog);
    const session = { dialog: dialog, trigger: trigger, cancelled: false };
    active = session;
    function dismiss() {
      session.cancelled = true;
      if (dialog.open) dialog.close();
      dialog.remove();
      if (active === session) active = null;
      if (trigger.isConnected) trigger.focus({ preventScroll: true });
    }
    close.addEventListener('click', dismiss);
    dialog.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); dismiss(); }
    });
    dialog.addEventListener('cancel', function (event) { event.preventDefault(); dismiss(); });
    dialog.addEventListener('click', function (event) { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dismiss(); } });
    async function attempt() {
      retry.hidden = true;
      close.focus();
      status.textContent = root.dataset.scWallLoading || 'Preparing your wall preview…';
      status.setAttribute('aria-busy', 'true');
      try {
        await prepare(root);
        if (session.cancelled || !root.isConnected) return;
        dismiss();
        root.scWallOpen();
      } catch (error) {
        if (session.cancelled) return;
        status.textContent = root.dataset.scWallError || 'Your wall preview could not load. Please try again.';
        retry.hidden = false;
        trigger.dispatchEvent(new CustomEvent('sc:wall-preview-error', { bubbles: true }));
      } finally { status.removeAttribute('aria-busy'); }
    }
    retry.addEventListener('click', attempt);
    dialog.showModal();
    attempt();
  }

  document.addEventListener('click', function (event) {
    const target = event.target instanceof Element ? event.target : event.target.parentElement;
    const trigger = target?.closest('[data-sc-wall-preview-trigger]');
    if (!trigger || trigger.disabled || trigger.getAttribute('aria-disabled') === 'true') return;
    event.preventDefault();
    if (active) { active.dialog.querySelector('button:not([hidden])')?.focus(); return; }
    const root = document.querySelector('.section-main-product [data-sc-wall-root]') || document.querySelector('[data-sc-wall-root]');
    if (!root) return;
    trigger.focus({ preventScroll: true });
    if (root.scWallOpen) root.scWallOpen();
    else loadingDialog(trigger, root);
  });
}());
