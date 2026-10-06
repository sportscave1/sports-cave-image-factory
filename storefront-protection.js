/* Sports Cave storefront deterrence. This cannot prevent OS screenshots. */
(() => {
  'use strict';
  if (window.__scProtectionInstalled) return;
  window.__scProtectionInstalled = true;
  const baseline = {enabled:true,disableRightClick:true,preventImageDragging:true,
    preventSelection:true,protectPrinting:true,blockSaveShortcuts:true,
    mobileTouchProtection:true,aggressiveCopyDeterrence:true,showCopyrightMessage:true};
  let config = baseline;
  const script = document.currentScript;
  const origin = script && new URL(script.src, location.href).origin;
  // Customer account/checkout and order-printing pages are outside this integration.
  if (/^\/(checkout|checkouts|account|orders)(\/|$)/.test(location.pathname)) return;
  const marker = '[data-sc-protected],.sc-protected-artwork';
  const media = '.product__media img,.product-media img,.product-single__photo,.product__media-item img,.card__media img';
  const editable = target => target instanceof Element && Boolean(target.closest('input,textarea,select,[contenteditable="true"],[role="textbox"]'));
  const protectedTarget = target => target instanceof Element && Boolean(target.closest(marker));
  const style = document.createElement('style');
  document.head.appendChild(style);
  let toast, lastToast = 0;
  function notify() {
    if (!config.showCopyrightMessage || Date.now()-lastToast < 5000) return;
    lastToast = Date.now();
    if (!toast) {
      toast = document.createElement('div'); toast.setAttribute('role','status');
      toast.style.cssText='position:fixed;bottom:20px;left:20px;z-index:1000;max-width:300px;background:#191815;color:#fff;padding:12px;border-radius:8px;font:12px sans-serif;pointer-events:none';
      toast.textContent='© Sports Cave — Limited Edition Artwork. Copying and unauthorised reproduction are prohibited.';
      document.body.appendChild(toast);
    }
    toast.hidden=false; setTimeout(() => {toast.hidden=true;},3000);
  }
  function apply() {
    // CSS carries dynamic policy; no costly scan on every DOM mutation.
    document.querySelectorAll(media).forEach(img => img.setAttribute('data-sc-protected','artwork'));
    document.querySelectorAll(marker).forEach(el => {
      if (el.tagName==='IMG') el.draggable=!(config.enabled && config.preventImageDragging);
    });
    style.textContent = !config.enabled ? '' :
      (config.preventSelection ? `${marker}{user-select:none;-webkit-user-select:none}` : '')+
      (config.mobileTouchProtection ? `${marker}{-webkit-touch-callout:none}` : '')+
      (config.protectPrinting ? `@media print{${marker}{visibility:hidden!important}}` : '');
  }
  document.addEventListener('contextmenu',event => {
    if (config.enabled && config.disableRightClick && !editable(event.target)) {event.preventDefault();if(protectedTarget(event.target))notify();}
  });
  document.addEventListener('dragstart',event => {
    if(config.enabled && config.preventImageDragging && protectedTarget(event.target) && !editable(event.target))event.preventDefault();
  });
  document.addEventListener('copy',event => {
    if(config.enabled && config.aggressiveCopyDeterrence && protectedTarget(event.target) && !editable(event.target)){event.preventDefault();notify();}
  });
  document.addEventListener('keydown',event => {
    if(!config.enabled || editable(event.target) || !(event.ctrlKey || event.metaKey))return;
    if((config.blockSaveShortcuts && event.key.toLowerCase()==='s') || (config.protectPrinting && event.key.toLowerCase()==='p')) {event.preventDefault();notify();}
  });
  let scheduled=false;
  const observer=new MutationObserver(changes => {
    if(scheduled || !changes.some(c => c.addedNodes.length))return;
    scheduled=true;setTimeout(() => {scheduled=false;apply();},150);
  });
  apply(); observer.observe(document.body,{childList:true,subtree:true});
  if(origin) {
    const controller=new AbortController();const timeout=setTimeout(() => controller.abort(),3000);
    fetch(`${origin}/api/storefront-protection/config`,{credentials:'omit',signal:controller.signal})
      .then(response => {if(!response.ok)throw new Error('Unavailable');return response.json();})
      .then(value => {const safe={...baseline};Object.keys(baseline).forEach(key => {if(typeof value[key]==='boolean')safe[key]=value[key];});config=safe;apply();})
      .catch(() => {}).finally(() => clearTimeout(timeout));
  }
})();
