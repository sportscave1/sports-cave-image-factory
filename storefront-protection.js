/* Sports Cave public Shopify artwork deterrence; cannot prevent OS screenshots. */
(() => {
  'use strict';
  // Never install on Sports Cave OS, checkout, accounts or order pages.
  if (!['sportscaveshop.com','www.sportscaveshop.com'].includes(location.hostname) ||
      /^\/(checkout|checkouts|account|orders)(\/|$)/.test(location.pathname) || window.__scProtectionInstalled) return;
  window.__scProtectionInstalled = true;
  const baseline = {enabled:true,disableRightClick:true,preventImageDragging:true,
    preventSelection:true,protectPrinting:true,blockSaveShortcuts:true,
    mobileTouchProtection:true,aggressiveCopyDeterrence:true,showCopyrightMessage:true,visibleWatermark:false};
  let config = baseline;
  const script = document.currentScript;
  const origin = script && new URL(script.src, location.href).origin;
  const marker = '[data-sc-protected="artwork"],.sc-protected-artwork';
  const media = '.product__media img,.product-media img,.product-single__photo,.product__media-item img,.card__media img,.product-gallery img,.product-block__image img,.product-detail__images img,.product-block .rimage__image';
  const excluded = 'input,textarea,select,button,[contenteditable],[role="textbox"],[role="button"],.sc-wall-v1,[data-sc-wall-overlay],[data-sc-wall-visualizer],dialog,[role="dialog"]';
  const editable = target => target instanceof Element && Boolean(target.closest(excluded));
  const protectedTarget = target => target instanceof Element && !editable(target) && Boolean(target.closest(marker));
  const style = document.createElement('style'); document.head.appendChild(style);
  let toast, lastToast = 0, hovered = null;
  const originalDrag = new WeakMap();
  const watermarks = new Map();
  function notify() {
    if (!config.showCopyrightMessage || Date.now()-lastToast < 5000) return;
    lastToast = Date.now();
    if (!toast) {
      toast = document.createElement('div'); toast.setAttribute('role','status');
      toast.style.cssText='position:fixed;bottom:20px;left:20px;z-index:1000;max-width:280px;background:#191815;color:#fff;padding:10px;border-radius:8px;font:12px sans-serif;pointer-events:none';
      toast.textContent='© Sports Cave — Artwork may not be copied or reproduced without permission.';
      document.body.appendChild(toast);
    }
    toast.hidden=false; setTimeout(() => {toast.hidden=true;},2000);
  }
  function apply() {
    document.querySelectorAll(media).forEach(img => {if(!editable(img)) img.setAttribute('data-sc-protected','artwork');});
    document.querySelectorAll(marker).forEach(el => {
      if(editable(el)) return;
      if(el.tagName==='IMG') {
        if(!originalDrag.has(el)) originalDrag.set(el,el.getAttribute('draggable'));
        if(config.enabled && config.preventImageDragging) el.draggable=false;
        else if(originalDrag.get(el)===null) el.removeAttribute('draggable');
        else el.setAttribute('draggable',originalDrag.get(el));
        const parent=el.parentElement;
        if(config.enabled && config.visibleWatermark && parent && !watermarks.has(parent)) {
          const label=document.createElement('span');label.className='sc-artwork-watermark';
          label.textContent='© Sports Cave';label.setAttribute('aria-hidden','true');
          const positioned=getComputedStyle(parent).position==='static';
          if(positioned) parent.classList.add('sc-artwork-watermark-host');
          parent.appendChild(label);watermarks.set(parent,{label,positioned});
        }
      }
    });
    watermarks.forEach(({label,positioned},parent)=>{
      if(!config.enabled || !config.visibleWatermark || !parent.isConnected){label.remove();if(positioned)parent.classList.remove('sc-artwork-watermark-host');watermarks.delete(parent);}
    });
    const scope=':is('+marker+'):not('+excluded+')';
    style.textContent = !config.enabled ? '' :
      (config.preventSelection ? `${scope}{user-select:none;-webkit-user-select:none}` : '')+
      (config.mobileTouchProtection ? `${scope}{-webkit-touch-callout:none}` : '')+
      `${scope} :is(input,textarea,select,button,[contenteditable]){user-select:auto;-webkit-user-select:auto;-webkit-touch-callout:default}`+
      (config.protectPrinting ? `@media print{${scope}{visibility:hidden!important}}` : '')+
      '.sc-artwork-watermark-host{position:relative}.sc-artwork-watermark{position:absolute;right:8px;bottom:8px;pointer-events:none;color:white;text-shadow:0 1px 3px #000;font:11px sans-serif;opacity:.55;z-index:1}';
  }
  document.addEventListener('contextmenu',event => {
    if(config.enabled && config.disableRightClick && protectedTarget(event.target)){event.preventDefault();notify();}
  });
  document.addEventListener('dragstart',event => {
    if(config.enabled && config.preventImageDragging && protectedTarget(event.target))event.preventDefault();
  });
  document.addEventListener('copy',event => {
    const selection=window.getSelection();
    const selected=selection && protectedTarget(selection.anchorNode?.parentElement);
    if(config.enabled && config.aggressiveCopyDeterrence && !editable(event.target) && (protectedTarget(event.target)||selected)){event.preventDefault();notify();}
  });
  document.addEventListener('pointerover',event=>{hovered=protectedTarget(event.target)?event.target:null;},{passive:true});
  document.addEventListener('pointerout',event=>{hovered=protectedTarget(event.relatedTarget)?event.relatedTarget:null;},{passive:true});
  document.addEventListener('keydown',event => {
    if(config.enabled && config.blockSaveShortcuts && !editable(event.target) &&
       (protectedTarget(event.target)||protectedTarget(hovered)) && (event.ctrlKey||event.metaKey) && event.key.toLowerCase()==='s') {event.preventDefault();notify();}
  });
  // One debounced scan only for added artwork, never pointer-move or polling work.
  let scheduled=false;
  new MutationObserver(changes=>{
    if(scheduled || !changes.some(c=>Array.from(c.addedNodes).some(n=>n instanceof Element &&
       (n.matches(media+','+marker)||n.querySelector(media+','+marker)))))return;
    scheduled=true;setTimeout(()=>{scheduled=false;apply();},150);
  }).observe(document.body,{childList:true,subtree:true});
  apply();
  if(origin) {
    const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),3000);
    fetch(`${origin}/api/storefront-protection/config`,{credentials:'omit',signal:controller.signal})
      .then(response=>{if(!response.ok)throw new Error('Unavailable');return response.json();})
      .then(value=>{const safe={...baseline};Object.keys(baseline).forEach(key=>{if(typeof value[key]==='boolean')safe[key]=value[key];});config=safe;apply();})
      .catch(()=>{}).finally(()=>clearTimeout(timeout));
  }
})();
