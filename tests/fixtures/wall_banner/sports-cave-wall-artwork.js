(function(){
'use strict';
if(window.SportsCaveWallArtwork)return;

var ROOT_SELECTOR='[data-sc-wall-root]';
var CROPS={black:{x:30,y:151,w:930,h:692},oak:{x:27,y:148,w:938,h:696},white:{x:31,y:148,w:934,h:696},unframed:{x:85,y:208,w:822,h:581}};
var SOURCE_SIZE=1000;
function clamp(value,min,max){return Math.min(max,Math.max(min,value));}
function clean(value){return String(value||'').replace(/\s+/g,' ').trim();}
function makeId(){if(window.crypto.randomUUID) return window.crypto.randomUUID();var bytes=new Uint8Array(16);window.crypto.getRandomValues(bytes);bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;var hex=Array.from(bytes,function(b){return b.toString(16).padStart(2,'0');}).join('');return hex.slice(0,8)+'-'+hex.slice(8,12)+'-'+hex.slice(12,16)+'-'+hex.slice(16,20)+'-'+hex.slice(20);}
function browserSessionId(){var key='sc_wall_session_id_v2';try{var existing=(window.sessionStorage.getItem(key)||'').replace(/^session-/,'');if(!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(existing)) existing=makeId();window.sessionStorage.setItem(key,existing);return existing;}catch(error){return makeId();}}
function roundSmart(value,unit){var n=Number(value||0);if(!Number.isFinite(n)) return '';if(unit==='cm'&&Math.abs(n-Math.round(n))<0.05) return String(Math.round(n));return String(Math.round(n*10)/10);}
function frameName(key){if(key==='oak') return 'Oak Frame';if(key==='white') return 'White Frame';if(key==='unframed') return 'Unframed';return 'Black Frame';}
function normalizeFrame(value){var text=String(value||'').toLowerCase();if(text.indexOf('unframed')>-1||text.indexOf('poster only')>-1||text.indexOf('poster-only')>-1) return 'unframed';if(text.indexOf('oak')>-1) return 'oak';if(text.indexOf('white')>-1) return 'white';return 'black';}
function sizeTokenFromRaw(raw,index,cmPair){var match=clean(raw).toUpperCase().match(/(^|\s)(XL|L|M|S)(?=\s|\-|$)/);if(match) return match[2];var maxCm=cmPair&&cmPair.length===2?Math.max(cmPair[0],cmPair[1]):0;if(maxCm>=80) return 'XL';if(maxCm>=55) return 'L';if(maxCm>=38) return 'M';if(maxCm>0) return 'S';return ['XL','L','M','S'][Number(index)]||'SIZE';}
function parsePair(raw,unit){var re=unit==='cm'?/(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*cm/i:/(\d+(?:\.\d+)?)\s*[×xX]\s*(\d+(?:\.\d+)?)\s*in/i;var match=String(raw||'').match(re);if(!match) return null;return [Number(match[1]),Number(match[2])];}
function parseSizeInfo(raw,index){var cm=parsePair(raw,'cm');var inches=parsePair(raw,'in');if(!cm&&inches) cm=[inches[0]*2.54,inches[1]*2.54];if(!inches&&cm) inches=[cm[0]/2.54,cm[1]/2.54];if(!cm) cm=[21,30];if(!inches) inches=[cm[0]/2.54,cm[1]/2.54];return {raw:clean(raw),token:sizeTokenFromRaw(raw,index,cm),cm:cm,inches:inches,widthCm:Math.max(cm[0],cm[1]),heightCm:Math.min(cm[0],cm[1]),widthIn:Math.max(inches[0],inches[1]),heightIn:Math.min(inches[0],inches[1])};}
function formatSize(info,unit){if(!info) return '';var pair=unit==='in'?info.inches:info.cm;return roundSmart(pair[0],unit)+' × '+roundSmart(pair[1],unit)+' '+unit;}

function productPickerFor(root){var picker=null;var section=root&&root.closest?root.closest('[id^="shopify-section-"],.shopify-section'):null;if(section) picker=section.querySelector('variant-picker.sc-vp');if(!picker&&root&&root.closest){var host=root.closest('product-info,.product,.product-info,[data-product-id]');if(host) picker=host.querySelector('variant-picker.sc-vp');}return picker||document.querySelector('variant-picker.sc-vp');}
function currentFrameFromPicker(root){var picker=productPickerFor(root);if(!picker) return 'black';var groups=picker.querySelectorAll('.option-selector');for(var i=0;i<groups.length;i+=1){var optionName=String(groups[i].getAttribute('data-option')||'').toLowerCase();if(optionName.indexOf('frame')===-1&&optionName.indexOf('style')===-1) continue;var selected=groups[i].querySelector('input[type="radio"]:checked');if(selected) return normalizeFrame(selected.value);}return 'black';}
function currentSizeFromPicker(root){var picker=productPickerFor(root);if(!picker) return '';var groups=picker.querySelectorAll('.option-selector');for(var i=0;i<groups.length;i+=1){var optionName=String(groups[i].getAttribute('data-option')||'').toLowerCase();if(optionName.indexOf('size')===-1) continue;var selected=groups[i].querySelector('input[type="radio"]:checked');if(selected) return clean(selected.value);}return '';}
function currentUnitFromPicker(root){var picker=productPickerFor(root);if(!picker) return '';var attr=String(picker.getAttribute('data-unit')||'').toLowerCase();if(attr==='cm'||attr==='in') return attr;var pressed=picker.querySelector('[data-unit-btn][aria-pressed="true"]');if(pressed){var value=String(pressed.getAttribute('data-unit-btn')||pressed.textContent||'').toLowerCase().trim();if(value==='cm'||value==='in') return value;}return '';}


// One crop renderer and image cache for the existing modal and passive banner surfaces.
var cache={},imagePromiseCache={},renderedArtwork=new WeakMap();
function loadImage(url){if(!url)return Promise.reject(new Error('No product image available'));if(cache[url])return Promise.resolve(cache[url]);if(imagePromiseCache[url])return imagePromiseCache[url];imagePromiseCache[url]=new Promise(function(resolve,reject){var image=new Image();image.crossOrigin='anonymous';image.decoding='async';image.onload=function(){cache[url]=image;delete imagePromiseCache[url];resolve(image);};image.onerror=function(){delete imagePromiseCache[url];reject(new Error('Unable to load product image'));};image.src=url;});return imagePromiseCache[url];}
function artworkSource(root,frame){if(frame==='oak')return root.getAttribute('data-oak-url')||root.getAttribute('data-black-url')||'';if(frame==='white')return root.getAttribute('data-white-url')||root.getAttribute('data-black-url')||'';return root.getAttribute('data-black-url')||'';}
function renderProductArtwork(root,frame){
 var url=artworkSource(root,frame),key=frame+'|'+url,entries=renderedArtwork.get(root);
 if(!entries){entries=new Map();renderedArtwork.set(root,entries);}
 if(entries.has(key))return entries.get(key);
 if(entries.size>=2)entries.delete(entries.keys().next().value);
 var promise=loadImage(url).then(function(image){
  var crop=CROPS[frame]||CROPS.black,canvas=document.createElement('canvas');
  canvas.width=Math.round(crop.w*2);canvas.height=Math.round(crop.h*2);
  var ctx=canvas.getContext('2d'),scaleX=image.naturalWidth/SOURCE_SIZE,scaleY=image.naturalHeight/SOURCE_SIZE;
  ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';
  ctx.drawImage(image,crop.x*scaleX,crop.y*scaleY,crop.w*scaleX,crop.h*scaleY,0,0,canvas.width,canvas.height);
  return canvas;
 }).catch(function(error){entries.delete(key);throw error;});
 entries.set(key,promise);return promise;
}
function artworkConfiguration(root){
 var frame=currentFrameFromPicker(root),raw=currentSizeFromPicker(root),size=parseSizeInfo(raw,0),picker=productPickerFor(root),maximum=size.widthCm;
 if(picker)picker.querySelectorAll('.option-selector').forEach(function(group){
  if(String(group.getAttribute('data-option')||'').toLowerCase().indexOf('size')<0)return;
  group.querySelectorAll('input[type="radio"]').forEach(function(input,index){maximum=Math.max(maximum,parseSizeInfo(input.value,index).widthCm);});
 });
 return {frame:frame,frameName:frameName(frame),size:size,unit:currentUnitFromPicker(root),scale:Math.sqrt(size.widthCm/maximum),productId:root.getAttribute('data-product-id'),productTitle:root.getAttribute('data-product-title')};
}
window.SportsCaveWallArtwork={helpers:{clamp:clamp,clean:clean,makeId:makeId,browserSessionId:browserSessionId,frameName:frameName,parseSizeInfo:parseSizeInfo,formatSize:formatSize,currentFrameFromPicker:currentFrameFromPicker,currentSizeFromPicker:currentSizeFromPicker,currentUnitFromPicker:currentUnitFromPicker,productPickerFor:productPickerFor,loadImage:loadImage},render:renderProductArtwork,configuration:artworkConfiguration,picker:productPickerFor};
document.dispatchEvent(new CustomEvent('sports-cave:wall-artwork-ready'));


}());

