// One outstanding native fragment request. Bounded retries; hidden listboxes
// and inert/aria-hidden descendants cannot hold optional reads indefinitely.
(() => {
  const {key, seconds, dialog} = CONFIG;
  window.scAutoTimers ??= {};
  clearTimeout(window.scAutoTimers[key]);
  if (window.scAutoRequest?.key === key) window.scAutoRequest = null;
  const deadline = Date.now() + 60000;
  if (!window.scAutoInputPriority) {
    window.scAutoInputPriority = true;
    const prioritise = event => {
      if (event.isTrusted && event.target.closest?.('.st-key-crm-workspace,[data-testid="stPopoverBody"]')) window.scAutoInputUntil = Date.now() + 1000;
    };
    for (const type of ['pointerdown','keydown','focusin']) document.addEventListener(type, prioritise, true);
  }
  const selectors = dialog ? '[data-testid=stPopoverBody],[role=listbox]' : '[role=dialog],[data-testid=stPopoverBody],[role=listbox]';
  const visible = el => {
    if (el.closest('[hidden],[inert],[aria-hidden="true"]') || !el.getClientRects().length) return false;
    const style = getComputedStyle(el);
    return style.visibility !== 'hidden' && style.display !== 'none' && Number(style.opacity) !== 0;
  };
  const retry = delay => { if (Date.now() < deadline) window.scAutoTimers[key] = setTimeout(tick, delay); };
  const tick = () => {
    if (!document.getElementById(key + '-controller')) return;
    const button = document.querySelector('.st-key-' + CSS.escape(key) + ' button');
    // One final settlement consumes the server's terminal read deadline even
    // when a dialog has stayed open throughout the normal refresh budget.
    if (Date.now() >= deadline) {
      if (button && !button.disabled) button.click();
      return;
    }
    if (!button || button.disabled || document.hidden || Date.now() < (window.scAutoInputUntil || 0) || [...document.querySelectorAll(selectors)].some(visible)
      || document.activeElement?.closest('[class*=st-key-auto-actions-]')) { retry(250); return; }
    if (window.scAutoRequest && !document.getElementById(window.scAutoRequest.key + '-controller')) window.scAutoRequest = null;
    if (window.scAutoRequest && Date.now() - window.scAutoRequest.at < 1000) { retry(100); return; }
    window.scAutoRequest = {key, at:Date.now()};
    button.click();
  };
  retry(Math.max(100, seconds * 1000));
})();
