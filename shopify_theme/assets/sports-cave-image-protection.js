/* Sports Cave storefront deterrence v2026-10-07.1; OS capture cannot be prevented. */
(()=>{
'use strict';
if(!['sportscaveshop.com','www.sportscaveshop.com'].includes(location.hostname)||/^(?:\/[a-z]{2}(?:-[a-z]{2})?)?\/(checkout|checkouts|account|orders)(\/|$)/i.test(location.pathname)||window.SportsCaveImageProtection||window.__scProtectionInstalled)return;
window.__scProtectionInstalled=true;
const script=document.currentScript,configUrl=script&&(script.dataset.scProtectionConfig||new URL('/api/storefront-protection/config',script.src).href);
const defaults={enabled:false,disableRightClick:true,preventImageDragging:true,preventSelection:true,protectPrinting:true,blockSaveShortcuts:true,mobileTouchProtection:true,aggressiveCopyDeterrence:true,showCopyrightMessage:false,visibleWatermark:false,protectProductImages:true,protectCollections:true,protectHomepage:true,protectWallPreview:true,screenshotDeterrence:true,wallPreviewWatermark:false,watermarkText:'Sports Cave',watermarkOpacity:.25,watermarkPosition:'bottom-right'};
const media='img,picture,video,canvas,svg image,[data-sc-protected="artwork"],.sc-protected-artwork',wallRoot='.sc-wall-v1,[data-sc-wall-overlay],[data-sc-wall-visualizer]',flags=['artwork','wall','selection','touch','drag','print'];
let config={...defaults},controller,observer,request,pending,generation=0;
const watermarks=new Set(),hosts=new Set();
const editable=el=>el instanceof Element&&!!el.closest('input,textarea,select,[contenteditable]:not([contenteditable="false"]),[role="textbox"]');
const path=e=>e.composedPath?e.composedPath():[e.target],editing=e=>path(e).some(editable);
function artworkEnabled(){const p=location.pathname.replace(/^\/[a-z]{2}(?:-[a-z]{2})?(?=\/|$)/i,'')||'/';return config[p==='/'?'protectHomepage':/^\/collections(\/|$)/.test(p)?'protectCollections':'protectProductImages'];}
function protectedElement(el){return el instanceof Element&&!editable(el)&&(el.closest(wallRoot)?config.protectWallPreview:artworkEnabled());}
function imageEvent(e){return !editing(e)&&path(e).some(el=>protectedElement(el)&&(el.matches(media)||el.closest('picture')||(el.matches('a')&&(el.querySelector(media)||/\.(?:avif|webp|png|jpe?g|gif|svg)(?:[?#]|$)/i.test(el.href)))));}
function removeStyles(){flags.forEach(k=>document.documentElement.removeAttribute('data-sc-protection-'+k));watermarks.forEach(e=>e.remove());watermarks.clear();hosts.forEach(e=>e.classList.remove('sc-artwork-watermark-host'));hosts.clear();}
function applyStyles(){const values={artwork:artworkEnabled(),wall:config.protectWallPreview,selection:config.preventSelection,touch:config.mobileTouchProtection,drag:config.preventImageDragging,print:config.protectPrinting};flags.forEach(k=>document.documentElement.setAttribute('data-sc-protection-'+k,String(values[k])));}
function stop(){if(controller)controller.abort();controller=null;if(observer)observer.disconnect();observer=null;removeStyles();}
function disable(){generation++;if(request)request.abort();request=null;pending=null;stop();config={...config,enabled:false};}
function watermark(){
 if(!config.visibleWatermark&&!config.wallPreviewWatermark)return;
 const marked=new WeakSet();
 const add=el=>{const wall=!!el.closest(wallRoot);if(!protectedElement(el)||!(wall?config.wallPreviewWatermark:config.visibleWatermark))return;const parent=wall?(el.closest('[data-sc-wall-stage],[data-sc-wall-live-camera]')||el.parentElement):el.parentElement;if(!parent||marked.has(parent))return;marked.add(parent);
 const label=document.createElement('span');label.className='sc-artwork-watermark';label.setAttribute('aria-hidden','true');label.textContent='© '+config.watermarkText;label.style.opacity=String(config.watermarkOpacity);label.style.cssText+=';'+(config.watermarkPosition==='center'?'left:50%;top:50%;transform:translate(-50%,-50%)':'right:8px;bottom:8px');
 if(getComputedStyle(parent).position==='static'&&!parent.classList.contains('sc-artwork-watermark-host')){parent.classList.add('sc-artwork-watermark-host');hosts.add(parent);}parent.appendChild(label);watermarks.add(label);};
 const scan=root=>{if(root instanceof Element&&root.matches(media))add(root);root.querySelectorAll(media).forEach(add);};scan(document);
 // Only optional watermarks require an observer. Protection itself never scans on mutations.
 observer=new MutationObserver(changes=>changes.forEach(c=>c.addedNodes.forEach(n=>{if(n instanceof Element&&!n.classList.contains('sc-artwork-watermark'))scan(n);})));observer.observe(document.documentElement,{childList:true,subtree:true});
}
function enable(){
 stop();if(!config.enabled)return;controller=new AbortController();const options={capture:true,signal:controller.signal};
 document.addEventListener('contextmenu',e=>{if(config.disableRightClick)e.preventDefault();},options);
 document.addEventListener('dragstart',e=>{if(config.preventImageDragging&&imageEvent(e))e.preventDefault();},options);
 document.addEventListener('selectstart',e=>{if(config.preventSelection&&imageEvent(e))e.preventDefault();},options);
 document.addEventListener('copy',e=>{const anchor=window.getSelection()?.anchorNode?.parentElement;if(config.aggressiveCopyDeterrence&&!editing(e)&&(imageEvent(e)||(anchor?.matches(media)&&protectedElement(anchor))))e.preventDefault();},options);
 document.addEventListener('keydown',e=>{if(editing(e))return;if(config.blockSaveShortcuts&&(e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s')e.preventDefault();if(config.screenshotDeterrence&&e.key==='PrintScreen')e.preventDefault();},options);
 applyStyles();watermark();
}
function update(value){
 if(!value||typeof value.enabled!=='boolean')return false;disable();config={...defaults};Object.keys(defaults).forEach(k=>{if(typeof defaults[k]==='boolean'&&typeof value[k]==='boolean')config[k]=value[k];});config.showCopyrightMessage=false;
 if(typeof value.watermarkText==='string'&&value.watermarkText.trim().length&&value.watermarkText.length<=60)config.watermarkText=value.watermarkText;
 if(typeof value.watermarkOpacity==='number'&&value.watermarkOpacity>=.05&&value.watermarkOpacity<=.6)config.watermarkOpacity=value.watermarkOpacity;
 if(['bottom-right','center'].includes(value.watermarkPosition))config.watermarkPosition=value.watermarkPosition;
 enable();window.__scProtectionReady=true;return true;
}
function refresh(){
 if(pending)return pending;if(!configUrl)return Promise.resolve(false);const seq=generation,active=new AbortController();request=active;const timeout=setTimeout(()=>active.abort(),5000);
 const job=fetch(configUrl,{credentials:'omit',signal:active.signal}).then(r=>{if(!r.ok)throw new Error('Unavailable');return r.json();}).then(value=>seq===generation?update(value):false).catch(()=>false).finally(()=>{clearTimeout(timeout);if(request===active)request=null;if(pending===job)pending=null;});pending=job;return job;
}
// Reinstallation and Shopify section reloads need no new listeners. No polling.
window.SportsCaveImageProtection=Object.freeze({version:'2026-10-07.1',enable:refresh,disable,update,refresh,get enabled(){return config.enabled;}});
refresh();
})();
