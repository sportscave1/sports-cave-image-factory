/* Sports Cave storefront-only deterrence v2026-10-06.2. OS screenshots cannot be blocked. */
(() => {
  'use strict';
  if (!['sportscaveshop.com','www.sportscaveshop.com'].includes(location.hostname) ||
      /^\/(checkout|checkouts|account|orders)(\/|$)/.test(location.pathname) || window.__scProtectionInstalled) return;
  window.__scProtectionInstalled = true;
  const script = document.currentScript;
  const origin = script && new URL(script.src, location.href).origin;
  const defaults = {enabled:true,disableRightClick:true,preventImageDragging:true,preventSelection:true,
    protectPrinting:true,blockSaveShortcuts:true,mobileTouchProtection:true,aggressiveCopyDeterrence:true,
    showCopyrightMessage:true,visibleWatermark:false,protectProductImages:true,protectCollections:true,
    protectHomepage:true,protectWallPreview:true,screenshotDeterrence:true,wallPreviewWatermark:false,
    watermarkText:'Sports Cave',watermarkOpacity:0.25,watermarkPosition:'bottom-right'};
  let config = {...defaults,enabled:false}, selector = '', hovered = null;
  const wallRoot = '.sc-wall-v1,[data-sc-wall-overlay],[data-sc-wall-visualizer]';
  const wallMedia = '.sc-wall-v1 img,.sc-wall-v1 canvas,.sc-wall-v1 video,[data-sc-wall-overlay] img,[data-sc-wall-overlay] canvas,[data-sc-wall-overlay] video';
  const marker = '[data-sc-protected="artwork"],.sc-protected-artwork';
  const media = '.product__media img,.product-media img,.product-single__photo,.product__media-item img,.card__media img,.product-gallery img,.product-block__image img,.product-detail__images img,.product-block .rimage__image,.product-media-modal img,.product-lightbox img,.schero__img,.sc-shop-by-sport__image,.sc-featured-collection-banner__frame img,.sc-square-mobile-zoom img,.sc-square-mobile-thumb img,.thumbnail--media-image img,.sc-desktop-featured__media img,.scmm-featured-card__media img,.sc-product-media img,.gallery-viewer img,.sc-legacy__image';
  const editable = el => el instanceof Element && !!el.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"]');
  const protectedTarget = el => config.enabled && el instanceof Element && !editable(el) && selector && !!el.closest(selector);
  const style = document.createElement('style'); document.head.appendChild(style);
  let toast, lastToast = 0;
  function notify() {
    if (!config.showCopyrightMessage || Date.now()-lastToast<5000) return;
    lastToast=Date.now();
    if (!toast) {
      toast=document.createElement('div');toast.setAttribute('role','status');
      toast.style.cssText='position:fixed;bottom:20px;left:20px;z-index:2147483647;max-width:280px;background:#191815;color:#fff;padding:10px;border-radius:8px;font:12px sans-serif;pointer-events:none';
      toast.textContent='© Sports Cave — Please use the official download where available. Screenshots and copying are not authorised.';
      document.body.appendChild(toast);
    }
    toast.hidden=false;setTimeout(()=>{toast.hidden=true;},2000);
  }
  function apply() {
    const scopeFlag=location.pathname==='/'?'protectHomepage':/^\/collections(\/|$)/.test(location.pathname)?'protectCollections':'protectProductImages';
    const scopes=[];
    if(config[scopeFlag]) scopes.push(`:is(${media},${marker}):not(:is(${wallRoot}) *)`);
    if(config.protectWallPreview) scopes.push(wallMedia);
    selector=scopes.length?`:is(${scopes.join(',')})`:'';
    if(!config.enabled || !selector) return;
    style.textContent=(config.preventSelection?`${selector}{user-select:none;-webkit-user-select:none}`:'')+
      (config.mobileTouchProtection?`${selector}{-webkit-touch-callout:none}`:'')+
      (config.preventImageDragging?`${selector}{-webkit-user-drag:none}`:'')+
      (config.protectPrinting?`@media print{${selector}{visibility:hidden!important}}`:'')+
      '.sc-artwork-watermark-host{position:relative}.sc-artwork-watermark{position:absolute;pointer-events:none!important;color:white;text-shadow:0 1px 3px #000;font:12px sans-serif;z-index:2}';
    // Only watermarking needs DOM work. Process added subtrees, never rescan the document on mutations.
    if(config.visibleWatermark || config.wallPreviewWatermark) {
      const marked=new WeakSet();
      const add=el=>{
        const wall=!!el.closest(wallRoot);
        if(!protectedTarget(el) || !(wall?config.wallPreviewWatermark:config.visibleWatermark)) return;
        const parent=wall?(el.closest('[data-sc-wall-stage],[data-sc-wall-live-camera]')||el.parentElement):el.parentElement;
        if(!parent || marked.has(parent)) return;
        marked.add(parent);
        const label=document.createElement('span');label.className='sc-artwork-watermark';label.setAttribute('aria-hidden','true');
        label.textContent='© '+config.watermarkText;
        label.style.opacity=String(config.watermarkOpacity);
        label.style.cssText+=';'+(config.watermarkPosition==='center'?'left:50%;top:50%;transform:translate(-50%,-50%)':'right:8px;bottom:8px');
        if(getComputedStyle(parent).position==='static')parent.classList.add('sc-artwork-watermark-host');
        parent.appendChild(label);
      };
      const scan=root=>{if(root instanceof Element && root.matches(selector))add(root);root.querySelectorAll(selector).forEach(add);};
      scan(document);
      new MutationObserver(changes=>changes.forEach(c=>c.addedNodes.forEach(n=>{
        if(n instanceof Element && !n.classList.contains('sc-artwork-watermark'))scan(n);
      }))).observe(document.body,{childList:true,subtree:true});
    }
  }
  document.addEventListener('contextmenu',e=>{if(config.disableRightClick && protectedTarget(e.target)){e.preventDefault();notify();}});
  document.addEventListener('dragstart',e=>{if(config.preventImageDragging && protectedTarget(e.target))e.preventDefault();});
  document.addEventListener('copy',e=>{
    const selection=window.getSelection();
    if(config.aggressiveCopyDeterrence && !editable(e.target) && (protectedTarget(e.target)||protectedTarget(selection?.anchorNode?.parentElement))){e.preventDefault();notify();}
  });
  document.addEventListener('pointerover',e=>{hovered=protectedTarget(e.target)?e.target:null;},{passive:true});
  document.addEventListener('pointerout',e=>{hovered=protectedTarget(e.relatedTarget)?e.relatedTarget:null;},{passive:true});
  document.addEventListener('keydown',e=>{
    if(editable(e.target))return;
    if(protectedTarget(e.target)||protectedTarget(hovered)||(config.enabled && config.protectWallPreview && document.querySelector('[data-sc-wall-overlay]:not([hidden])'))){
      if(config.blockSaveShortcuts && (e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='s'){e.preventDefault();notify();}
      // Notification only: this does NOT intercept hardware/system screenshot APIs.
      if(config.screenshotDeterrence && e.key==='PrintScreen')notify();
    }
  });
  // One bounded config request per page, no polling, fail open during backend outages.
  if(origin){
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),3000);
    fetch(origin+'/api/storefront-protection/config',{credentials:'omit',signal:controller.signal})
      .then(r=>{if(!r.ok)throw new Error('Unavailable');return r.json();})
      .then(value=>{
        if(!value || typeof value.enabled!=='boolean')return;
        config={...defaults};Object.keys(defaults).forEach(k=>{if(typeof defaults[k]==='boolean' && typeof value[k]==='boolean')config[k]=value[k];});
        if(typeof value.watermarkText==='string' && value.watermarkText.trim().length && value.watermarkText.length<=60)config.watermarkText=value.watermarkText;
        if(typeof value.watermarkOpacity==='number' && value.watermarkOpacity>=0.05 && value.watermarkOpacity<=0.6)config.watermarkOpacity=value.watermarkOpacity;
        if(['bottom-right','center'].includes(value.watermarkPosition))config.watermarkPosition=value.watermarkPosition;
        apply();window.__scProtectionReady=true;
      }).catch(()=>{}).finally(()=>clearTimeout(timeout));
  }
})();
