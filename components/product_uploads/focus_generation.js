(() => {
  const host = window.parent;
  const storageKey = 'product-upload-generation-focus';
  if (host.sessionStorage.getItem(storageKey) === focusToken) return;
  const route = host.location.href;
  let timer, stopped = false, previous = '', stable = 0, attempts = 0;
  const inputs = ['wheel', 'touchstart', 'pointerdown', 'keydown'];
  function cleanup() {
    stopped = true;
    clearTimeout(timer);
    inputs.forEach(type => host.removeEventListener(type, cancel, true));
    host.removeEventListener('popstate', cancel);
    removeEventListener('pagehide', cleanup);
  }
  function cancel() {
    // Explicit user navigation wins, including after a subsequent rerender.
    host.sessionStorage.setItem(storageKey, focusToken);
    cleanup();
  }
  function check() {
    if (stopped) return;
    if (host.location.href !== route || ++attempts > 50) return cleanup();
    const target = host.document.querySelector('.st-key-product-upload-generation');
    const main = target?.closest('[data-testid="stMain"]');
    const gallery = target?.querySelector('iframe[title="product_upload_gallery.product_upload_gallery"]');
    let ready = false;
    try {
      const images = [...(gallery?.contentDocument?.querySelectorAll('.gallery img') || [])];
      ready = images.length > 0 && images.every(image => image.complete && image.naturalWidth > 0);
    } catch (_) { /* Wait for the same-origin component to mount. */ }
    const rect = target?.getBoundingClientRect();
    const size = gallery?.getBoundingClientRect();
    if (main && ready && rect.height > 0 && size.height > 0) {
      // Observe actual component resizing, not merely the first DOM insertion.
      const layout = [rect.top + main.scrollTop, rect.width, rect.height, size.height].map(Math.round).join(':');
      stable = layout === previous ? stable + 1 : 0;
      previous = layout;
      if (stable >= 2) {
        const header = host.document.getElementById('sports-cave-os-top-bar');
        const inset = Math.max(main.getBoundingClientRect().top, header?.getBoundingClientRect().bottom || 0) + 12;
        // Scroll only the app's content viewport; never its shell/iframe ancestors.
        main.scrollTo({top: Math.max(0, main.scrollTop + rect.top - inset), behavior: 'instant'});
        host.sessionStorage.setItem(storageKey, focusToken);
        cleanup();
        return;
      }
    } else { stable = 0; previous = ''; }
    timer = setTimeout(check, 100);
  }
  inputs.forEach(type => host.addEventListener(type, cancel, {capture: true, passive: true}));
  host.addEventListener('popstate', cancel);
  addEventListener('pagehide', cleanup, {once: true});
  check();
})();
