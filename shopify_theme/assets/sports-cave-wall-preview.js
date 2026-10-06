(function(){
'use strict';
if(window.__scWallPreviewInstalled)return;window.__scWallPreviewInstalled=true;

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

function init(root,openImmediately){
if(!root||root.getAttribute('data-sc-wall-initialized')==='1') return;
root.setAttribute('data-sc-wall-initialized','1');
var detach=[];function listen(target,type,handler,options){target.addEventListener(type,handler,options);detach.push(function(){target.removeEventListener(type,handler,options);});}
root.scWallDestroy=function(){closeDialog();stopLiveCamera();detach.forEach(function(remove){remove();});detach=[];window.clearTimeout(resizeTimer);if(objectUrl)URL.revokeObjectURL(objectUrl);root.removeAttribute('data-sc-wall-initialized');};

var overlay=root.querySelector('[data-sc-wall-overlay]');
var dialog=root.querySelector('[data-sc-wall-dialog]');
var modal=root.querySelector('[data-sc-wall-modal]');
var openButton=root.querySelector('[data-sc-wall-open]');
var closeButton=root.querySelector('[data-sc-wall-close]');
var introCloseButton=root.querySelector('[data-sc-wall-intro-close]');
var cameraButton=root.querySelector('[data-sc-wall-camera]');
var uploadButton=root.querySelector('[data-sc-wall-upload]');
var cameraInput=root.querySelector('[data-sc-wall-camera-input]');
var uploadInput=root.querySelector('[data-sc-wall-upload-input]');
var liveCamera=root.querySelector('[data-sc-wall-live-camera]');
var cameraShell=liveCamera?liveCamera.querySelector('.sc-wall-v1__camera-shell'):null;
var cameraVideo=root.querySelector('[data-sc-wall-camera-video]');
var cameraHint=root.querySelector('[data-sc-wall-camera-hint]');
var cameraCapture=root.querySelector('[data-sc-wall-camera-capture]');
var cameraLibrary=root.querySelector('[data-sc-wall-camera-library]');
var cameraCancel=root.querySelector('[data-sc-wall-camera-cancel]');
var deviceNote=root.querySelector('[data-sc-wall-device-note]');
var intro=root.querySelector('[data-sc-wall-intro]');
var editor=root.querySelector('[data-sc-wall-editor]');
var stage=root.querySelector('[data-sc-wall-stage]');
var stageWrap=root.querySelector('.sc-wall-v1__stage-wrap');
var roomImage=root.querySelector('[data-sc-wall-room]');
var artCanvas=root.querySelector('[data-sc-wall-art]');
var artError=root.querySelector('[data-sc-wall-art-error]');
var artRetry=root.querySelector('[data-sc-wall-art-retry]');
if(artRetry)listen(artRetry,'click',function(){drawArtwork().then(function(){if(state.photoReady){if(state.calibrated)applyScaledSize();else applyQuickPreviewSize();}});});
var artFx=root.querySelector('[data-sc-wall-art-fx]');
var stageTone=root.querySelector('[data-sc-wall-stage-tone]');
var landscapeControls=root.querySelector('[data-sc-wall-landscape-controls]');
var landscapeScaleDock=root.querySelector('[data-sc-wall-landscape-scale-dock]');
var confirmPromptEl=root.querySelector('[data-sc-wall-confirm-placement]');
var confirmButton=root.querySelector('[data-sc-wall-confirm]');
var confirmLabel=root.querySelector('[data-sc-wall-confirm-label]');
var saveWrap=root.querySelector('[data-sc-wall-save-wrap]');
var saveButton=root.querySelector('[data-sc-wall-save]');
var saveLabel=root.querySelector('[data-sc-wall-save-label]');
var sharePreviewButton=root.querySelector('[data-sc-wall-share-preview]');
var sharePreviewLabel=root.querySelector('[data-sc-wall-share-label]');
var shareNote=root.querySelector('[data-sc-wall-share-note]');
var downloadGate=root.querySelector('[data-sc-wall-download-gate]');
var downloadClose=root.querySelector('[data-sc-wall-download-close]');
var downloadName=root.querySelector('[data-sc-wall-download-name]');
var downloadEmail=root.querySelector('[data-sc-wall-download-email]');
var downloadConsent=root.querySelector('[data-sc-wall-download-consent]');
var downloadError=root.querySelector('[data-sc-wall-download-error]');
var downloadConfirm=root.querySelector('[data-sc-wall-download-confirm]');
var placementGuide=root.querySelector('[data-sc-wall-placement-guide]');
var stickyBuy=root.querySelector('[data-sc-wall-sticky-buy]');
var keepBrowsing=root.querySelector('[data-sc-wall-keep-browsing]');
if(keepBrowsing) listen(keepBrowsing,'click',function(){fireLocalPreviewEvent('wall_preview_keep_browsing');closeDialog();});
var stickySecure=root.querySelector('[data-sc-wall-sticky-secure]');
var stickyCartLabel=root.querySelector('[data-sc-wall-cart-label]');
var stickyCartPrice=root.querySelector('[data-sc-wall-cart-price]');
var stickyCartError=root.querySelector('[data-sc-wall-cart-error]');
var previewChip=root.querySelector('[data-sc-wall-preview-chip]');
var previewChipClose=root.querySelector('[data-sc-wall-preview-chip-close]');
var frameLabel=root.querySelector('[data-sc-wall-frame-label]');
var sizeSummary=root.querySelector('[data-sc-wall-size-summary]');
var sizeButtons=Array.prototype.slice.call(root.querySelectorAll('[data-sc-wall-size-option]'));
var measurementUnit=root.querySelector('[data-sc-wall-measurement-unit]');
var scaleUnitInline=root.querySelector('[data-sc-wall-scale-unit-inline]');
var referenceMeasurement=root.querySelector('[data-sc-wall-reference-measurement]');
var scaleHelp=root.querySelector('[data-sc-wall-scale-help]');
var scaleHelpClose=root.querySelector('[data-sc-wall-scale-help-close]');
var scaleHelpReopen=root.querySelector('[data-sc-wall-scale-help-reopen]');
var scaleHelpTitle=root.querySelector('[data-sc-wall-scale-help-title]');
var tapDemo=root.querySelector('[data-sc-wall-tap-demo]');
var scaleCopyStart=root.querySelector('[data-sc-wall-scale-copy-start]');
var scaleCopySecond=root.querySelector('[data-sc-wall-scale-copy-second]');
var scaleCopyMeasure=root.querySelector('[data-sc-wall-scale-copy-measure]');
var scaleEntry=root.querySelector('[data-sc-wall-scale-entry]');
var quickPreviewButton=root.querySelector('[data-sc-wall-quick-preview]');
var quickBadge=root.querySelector('[data-sc-wall-quick-badge]');
var submitMeasurementButton=root.querySelector('[data-sc-wall-submit-measurement]');
var flowError=root.querySelector('[data-sc-wall-flow-error]');
var measureLine=root.querySelector('[data-sc-wall-measure-line]');
var pointAEl=root.querySelector('[data-sc-wall-point-a]');
var pointBEl=root.querySelector('[data-sc-wall-point-b]');
var tapInstruction=root.querySelector('[data-sc-wall-tap-instruction]');
var resetButton=root.querySelector('[data-sc-wall-reset]');
var retakeButton=root.querySelector('[data-sc-wall-retake]');

if(!overlay||!dialog||!modal||!openButton||!closeButton||!stage||!roomImage||!artCanvas) return;

var productData={options:[],variants:[]};
var productDataNode=root.querySelector('[data-sc-wall-product-data]');
if(productDataNode){try{productData=JSON.parse(productDataNode.textContent||'{}')||productData;}catch(error){}}
var PRODUCT_OPTS=Array.isArray(productData.options)?productData.options:[];
var VARIANTS=Array.isArray(productData.variants)?productData.variants:[];
var FORMATTED=productData.formatted&&typeof productData.formatted==='object'?productData.formatted:{};

var context=artCanvas.getContext('2d');
var cache={},imagePromiseCache={};
var objectUrl='';
var assetRevision=0,assetPromise=null,saveTail=Promise.resolve();
var savedBlob=null;
var savedFile=null;
var savedBodyOverflow='';
var savedHtmlOverflow='';
var overlayHomeParent=overlay.parentNode;
var overlayHomeNext=overlay.nextSibling;
var logoUrl=root.getAttribute('data-logo-url')||'';
var cameraStream=null;var cameraRequestGeneration=0;
var cameraTrack=null;
var cameraImageCapture=null;
var cameraCaptureBusy=false;
var cameraHintTimer=0;
var captureFreezeCanvas=null;
var captureTransitionPending=false;
var cameraCaptureSeq=0;
var cameraZoomValue=1;
var cameraZoomMin=1;
var cameraZoomMax=3;
var cameraNativeZoom=false;
var cameraPinchStartDistance=0;
var cameraPinchStartZoom=1;
var cameraPendingZoom=1;
var cameraZoomRaf=0;
var cameraViewportRaf=0;
var cameraArtworkPrimePromise=null;
var photoLoadSeq=0;
var lastActiveElement=null;
var confirmTimer=0,archivePromise=null,lastArchiveBlob=null;var sessionId=browserSessionId();var state={frame:currentFrameFromPicker(root),unit:currentUnitFromPicker(root)||(root.getAttribute('data-unit')==='in'?'in':'cm'),sizeRaw:'',sizeInfo:null,photoReady:false,calibrated:false,calibrationActive:false,awaitingMeasurement:false,referenceMeasurement:0,pointA:null,pointB:null,centerX:50,centerY:44,artWidthPercent:42,dragging:false,dragPointerId:null,dragStartX:0,dragStartY:0,dragStartCenterX:50,dragStartCenterY:44,pageScrollX:0,pageScrollY:0,isMobileCamera:false,previewChipDismissed:false,upsizeCueArmed:false,upsizeCueConsumed:false,upsizeCueTargetRaw:'',clientPreviewId:makeId('preview'),previewId:'',shareUrl:'',storageSaved:false,storageAccepted:false,archiveStatus:'',confirmed:false,confirming:false,confirmPromptReady:false,hasDraggedPlacement:false,quickPreview:false,scaleHelpDismissed:false,hasPlacedOnce:false,photoLandscape:false,startedAt:new Date().toISOString()};

function sourceUrlFor(frame){if(frame==='oak') return root.getAttribute('data-oak-url')||root.getAttribute('data-black-url')||'';if(frame==='white') return root.getAttribute('data-white-url')||root.getAttribute('data-black-url')||'';return root.getAttribute('data-black-url')||'';}
function loadImage(url){if(!url)return Promise.reject(new Error('No product image available'));if(cache[url])return Promise.resolve(cache[url]);if(imagePromiseCache[url])return imagePromiseCache[url];imagePromiseCache[url]=new Promise(function(resolve,reject){var image=new Image();image.crossOrigin='anonymous';image.decoding='async';image.onload=function(){cache[url]=image;delete imagePromiseCache[url];resolve(image);};image.onerror=function(){delete imagePromiseCache[url];reject(new Error('Unable to load product image'));};image.src=url;});return imagePromiseCache[url];}
function warmCurrentArtwork(){var frame=currentFrameFromPicker(root);var sourceFrame=frame==='unframed'?'black':frame;var url=sourceUrlFor(sourceFrame);if(url&&!cache[url]) loadImage(url).catch(function(){});}
function setFlowError(text){if(flowError) flowError.textContent=text||'';}

function setShareNote(text,isError){if(!shareNote) return;shareNote.textContent=text||'';shareNote.style.color=isError?'#9B3D30':'#6F6A64';}
function loggedInIdentity(){var email=String(root.getAttribute('data-customer-email')||'').trim().toLowerCase();var name=String(root.getAttribute('data-customer-name')||'').trim();var customerId=String(root.getAttribute('data-customer-id')||'').trim();if(!email&&!customerId) return null;return {email:email,name:name,shopifyCustomerId:customerId,source:'logged_in'};}
var DOWNLOAD_IDENTITY_KEY='sc_wall_preview_download_identity_v1';
function validIdentityEmail(value){return /^[^\s@\/\\]+@[^\s@\/\\]+\.[^\s@\/\\]+$/.test(String(value||'').trim());}
function sessionDownloadIdentity(){try{var raw=window.sessionStorage.getItem(DOWNLOAD_IDENTITY_KEY);if(!raw) return null;var parsed=JSON.parse(raw);var email=String(parsed&&parsed.email||'').trim().toLowerCase();var name=clean(parsed&&parsed.name||'');if(!validIdentityEmail(email)) return null;return {email:email,name:name,shopifyCustomerId:'',source:'guest'};}catch(error){return null;}}
function rememberDownloadIdentity(identity){if(!identity||identity.source==='logged_in') return;try{window.sessionStorage.setItem(DOWNLOAD_IDENTITY_KEY,JSON.stringify({email:identity.email,name:identity.name}));}catch(error){}}
function setDownloadError(value){if(downloadError) downloadError.textContent=value||'';}
function openDownloadGate(){if(!downloadGate||!state.confirmed) return;var identity=loggedInIdentity()||sessionDownloadIdentity();if(downloadName) downloadName.value=identity&&identity.name?identity.name:'';if(downloadEmail) downloadEmail.value=identity&&identity.email?identity.email:'';if(downloadConsent) downloadConsent.checked=true;setDownloadError('');downloadGate.hidden=false;downloadGate.setAttribute('aria-hidden','false');window.setTimeout(function(){var target=(downloadName&&!downloadName.value)?downloadName:downloadEmail;if(target){try{target.focus();}catch(error){}}},30);}
function closeDownloadGate(){if(!downloadGate) return;downloadGate.setAttribute('aria-hidden','true');downloadGate.hidden=true;setDownloadError('');if(downloadConfirm){downloadConfirm.disabled=false;downloadConfirm.textContent='Download Preview';}}
function downloadIdentityFromGate(){var name=clean(downloadName?downloadName.value:'');var email=String(downloadEmail?downloadEmail.value:'').trim().toLowerCase();if(name.length<2){setDownloadError('Enter your name.');if(downloadName) downloadName.focus();return null;}if(!validIdentityEmail(email)){setDownloadError('Enter a valid email address.');if(downloadEmail) downloadEmail.focus();return null;}var logged=loggedInIdentity();return {email:email,name:name,shopifyCustomerId:logged&&logged.shopifyCustomerId?logged.shopifyCustomerId:'',source:logged&&logged.email===email?'logged_in':'guest'};}
function attributionParams(){var out={referrer:document.referrer||'',landing_url:window.location.href,utm_source:'',utm_medium:'',utm_campaign:'',utm_content:'',utm_term:''};try{var url=new URL(window.location.href);['utm_source','utm_medium','utm_campaign','utm_content','utm_term'].forEach(function(key){out[key]=url.searchParams.get(key)||'';});}catch(error){}return out;}
function isMobileCameraDevice(){var ua=navigator.userAgent||'';var touch=Number(navigator.maxTouchPoints||0)>0;var coarse=false;try{coarse=window.matchMedia&&window.matchMedia('(pointer: coarse)').matches;}catch(error){}return /Android|iPhone|iPad|iPod/i.test(ua)||(touch&&coarse);}
function applyDeviceMode(){state.isMobileCamera=isMobileCameraDevice();root.setAttribute('data-camera-mode',state.isMobileCamera?'mobile':'desktop');if(cameraButton) cameraButton.hidden=!state.isMobileCamera;if(cameraInput) cameraInput.disabled=!state.isMobileCamera;if(deviceNote) deviceNote.hidden=true;if(retakeButton) retakeButton.textContent=state.isMobileCamera?'Take Another Photo':'Choose Another Photo';}
function isImageUploadFile(file){if(!file) return false;var type=String(file.type||'').toLowerCase();if(type.indexOf('image/')===0) return true;var name=String(file.name||'').toLowerCase();return /\.(?:jpe?g|jpe|jfif|png|webp|avif|gif|bmp|heic|heif)$/i.test(name);}
function desktopUploadBlobFromCanvas(canvas,type,quality){return new Promise(function(resolve,reject){try{canvas.toBlob(function(blob){if(blob) resolve(blob);else reject(new Error('Could not normalize desktop image'));},type||'image/jpeg',quality||.96);}catch(error){reject(error);}});}
async function normalizeDesktopUploadFallback(file){
if(!file||state.isMobileCamera) return file;
if(typeof createImageBitmap!=='function') throw new Error('Desktop image decoder unavailable');
var bitmap=null;
try{
try{
bitmap=await createImageBitmap(file,{imageOrientation:'from-image',resizeWidth:4096,resizeQuality:'high'});
}catch(firstError){
try{bitmap=await createImageBitmap(file,{imageOrientation:'from-image'});}
catch(secondError){bitmap=await createImageBitmap(file);}
}
if(!bitmap||!bitmap.width||!bitmap.height) throw new Error('Desktop image could not be decoded');
var maxDim=4096,maxPixels=16000000;
var scale=Math.min(1,maxDim/bitmap.width,maxDim/bitmap.height,Math.sqrt(maxPixels/(bitmap.width*bitmap.height)));
var width=Math.max(1,Math.round(bitmap.width*scale));
var height=Math.max(1,Math.round(bitmap.height*scale));
var canvas=document.createElement('canvas');
canvas.width=width;
canvas.height=height;
var ctx=canvas.getContext('2d');
if(!ctx) throw new Error('Desktop image canvas unavailable');
ctx.imageSmoothingEnabled=true;
ctx.imageSmoothingQuality='high';
ctx.drawImage(bitmap,0,0,width,height);
var sourceType=String(file.type||'').toLowerCase();
var outputType=sourceType==='image/png'?'image/png':'image/jpeg';
var blob=await desktopUploadBlobFromCanvas(canvas,outputType,.96);
try{
var baseName=String(file.name||'wall-photo').replace(/\.[^.]+$/,'');
var extension=outputType==='image/png'?'.png':'.jpg';
return new File([blob],baseName+extension,{type:outputType,lastModified:file.lastModified||Date.now()});
}catch(fileError){
return blob;
}
}finally{
if(bitmap&&typeof bitmap.close==='function'){try{bitmap.close();}catch(error){}}
}
}
function setPreviewActionState(){var visible=!!(state.photoReady||captureTransitionPending);var ready=!!(state.photoReady&&previewIsReady()&&!artCanvas.hidden&&!state.calibrationActive&&!state.awaitingMeasurement&&!captureTransitionPending&&roomImage.naturalWidth&&roomImage.naturalHeight);if(saveWrap)saveWrap.hidden=!visible;if(saveButton)saveButton.disabled=!ready;if(sharePreviewButton)sharePreviewButton.disabled=!ready;}
function setStagePhotoState(){if(!stage) return;stage.classList.toggle('has-photo',!!state.photoReady);if(stageTone) stageTone.hidden=!state.photoReady;if(overlay) overlay.classList.toggle('is-photo-ready',!!state.photoReady);}

var landscapeMovables=[scaleHelp,scaleHelpReopen,tapInstruction,tapDemo,placementGuide,confirmPromptEl].filter(Boolean);
var landscapeAnchors=landscapeMovables.map(function(node){
var anchor=document.createComment('sc-wall-landscape-anchor');
if(node.parentNode) node.parentNode.insertBefore(anchor,node);
return {node:node,anchor:anchor};
});
function restoreLandscapeControls(){
landscapeAnchors.forEach(function(item){
if(item.anchor&&item.anchor.parentNode&&item.node.parentNode!==item.anchor.parentNode){
item.anchor.parentNode.insertBefore(item.node,item.anchor.nextSibling);
}
});
if(landscapeControls) landscapeControls.hidden=true;
root.classList.remove('sc-wall-v1--landscape-controls-below');
}
var landscapeScaleItems=[scaleHelp,scaleHelpReopen].filter(Boolean);
var landscapeScaleAnchors=landscapeScaleItems.map(function(node){
var anchor=document.createComment('sc-wall-landscape-scale-anchor');
if(node.parentNode) node.parentNode.insertBefore(anchor,node);
return {node:node,anchor:anchor};
});
function restoreLandscapeScaleDock(){
landscapeScaleAnchors.forEach(function(item){
if(item.anchor&&item.anchor.parentNode&&item.node.parentNode!==item.anchor.parentNode){
item.anchor.parentNode.insertBefore(item.node,item.anchor.nextSibling);
}
});
if(landscapeScaleDock){landscapeScaleDock.hidden=true;landscapeScaleDock.classList.remove('is-active');}
window.requestAnimationFrame(syncDesktopPreviewLayout);
}
function syncLandscapeScaleDock(){
var useDock=!!(landscapeScaleDock&&state.photoLandscape&&state.photoReady&&!state.quickPreview&&!state.calibrated&&(state.calibrationActive||state.awaitingMeasurement));
if(!useDock){restoreLandscapeScaleDock();return;}
landscapeScaleDock.hidden=false;
landscapeScaleDock.classList.add('is-active');
landscapeScaleItems.forEach(function(node){if(node.parentNode!==landscapeScaleDock) landscapeScaleDock.appendChild(node);});
if(desktopPreviewMode()) window.requestAnimationFrame(syncDesktopPreviewLayout);
}
function viewportIsLandscape(){
return Math.max(1,window.innerWidth||document.documentElement.clientWidth||1)>Math.max(1,window.innerHeight||document.documentElement.clientHeight||1);
}
function syncLandscapeControls(){

root.classList.toggle('sc-wall-v1--landscape-photo',!!state.photoLandscape);
if(overlay) overlay.classList.toggle('is-landscape-photo',!!state.photoLandscape);
restoreLandscapeControls();
root.classList.remove('sc-wall-v1--landscape-controls-below');
if(landscapeControls) landscapeControls.hidden=true;
syncLandscapeScaleDock();

}
function setPhotoLandscapeLayout(isLandscape){
state.photoLandscape=!!isLandscape;
syncLandscapeControls();
window.requestAnimationFrame(function(){positionMeasurementVisuals();requestArtworkEffectsSync();});
}
function previewIsReady(){return !state.artworkFailed&&!!(state.calibrated||state.quickPreview);}
function sampleRoomAverage(x,y,w,h){try{if(!roomImage||!roomImage.naturalWidth||!roomImage.naturalHeight) return null;var sx=Math.max(0,Math.round(x));var sy=Math.max(0,Math.round(y));var sw=Math.max(4,Math.round(w));var sh=Math.max(4,Math.round(h));if(sx>=roomImage.naturalWidth||sy>=roomImage.naturalHeight) return null;sw=Math.min(sw,roomImage.naturalWidth-sx);sh=Math.min(sh,roomImage.naturalHeight-sy);var canvas=document.createElement('canvas');canvas.width=24;canvas.height=24;var ctx=canvas.getContext('2d',{willReadFrequently:true});if(!ctx) return null;ctx.drawImage(roomImage,sx,sy,sw,sh,0,0,24,24);var data=ctx.getImageData(0,0,24,24).data;var r=0,g=0,b=0,c=0;for(var i=0;i<data.length;i+=4){if(data[i+3]<12) continue;r+=data[i];g+=data[i+1];b+=data[i+2];c++;}if(!c) return null;return {r:r/c,g:g/c,b:b/c};}catch(error){return null;}}
function liveArtworkLighting(){if(!roomImage||!roomImage.naturalWidth||!roomImage.naturalHeight||!artCanvas||artCanvas.hidden) return null;var artW=roomImage.naturalWidth*(state.artWidthPercent/100);var artH=artCanvas.width&&artCanvas.height?artW*(artCanvas.height/artCanvas.width):artW*0.75;var x=roomImage.naturalWidth*(state.centerX/100)-artW/2;var y=roomImage.naturalHeight*(state.centerY/100)-artH/2;var padX=Math.max(12,artW*.08);var padY=Math.max(12,artH*.08);var top=sampleRoomAverage(x+artW*.16,Math.max(0,y-padY),artW*.68,padY);var left=sampleRoomAverage(Math.max(0,x-padX),y+artH*.18,padX,artH*.64);var right=sampleRoomAverage(Math.min(roomImage.naturalWidth-4,x+artW),y+artH*.18,padX,artH*.64);var bottom=sampleRoomAverage(x+artW*.16,Math.min(roomImage.naturalHeight-4,y+artH),artW*.68,padY);var ambient=top||left||right||bottom;if(!ambient) return null;var luma=.2126*ambient.r+.7152*ambient.g+.0722*ambient.b;return {ambient:ambient,luma:luma,top:top,left:left,right:right,bottom:bottom};}
function applyLiveArtworkPhotorealism(){var lighting=liveArtworkLighting();if(!lighting||!stage) return;var warm=((lighting.ambient.r-lighting.ambient.b)/255);var bright=clamp((lighting.luma-122)/255,-.18,.18);stage.style.setProperty('--sc-art-ambient-rgb',Math.round(lighting.ambient.r)+','+Math.round(lighting.ambient.g)+','+Math.round(lighting.ambient.b));stage.style.setProperty('--sc-art-brightness',(0.988+bright*.16).toFixed(3));stage.style.setProperty('--sc-art-contrast',(0.992+bright*.04).toFixed(3));stage.style.setProperty('--sc-art-saturation',(0.99+Math.max(-.02,Math.min(.02,warm*.14))).toFixed(3));stage.style.setProperty('--sc-art-shadow-blur',Math.max(10,Math.round((artCanvas.getBoundingClientRect().width||100)*.055))+'px');stage.style.setProperty('--sc-art-shadow-y',Math.max(5,Math.round((artCanvas.getBoundingClientRect().width||100)*.02))+'px');stage.style.setProperty('--sc-art-shadow-alpha',(0.11+Math.max(0,.14-bright*.18)).toFixed(3));stage.style.setProperty('--sc-art-shadow-alpha-soft',(0.075+Math.max(0,.08-bright*.12)).toFixed(3));stage.style.setProperty('--sc-art-fx-opacity',(0.58+Math.max(0,bright*.12)).toFixed(3));stage.style.setProperty('--sc-art-glare-strong',(0.06+Math.max(0,bright*.1)).toFixed(3));stage.style.setProperty('--sc-art-glare-soft',(0.02+Math.max(0,bright*.04)).toFixed(3));stage.style.setProperty('--sc-art-ambient-alpha',(0.028+Math.abs(warm)*.035).toFixed(3));stage.style.setProperty('--sc-art-border-alpha',(0.028+Math.max(0,bright*.03)).toFixed(3));}
function syncArtworkEffects(){if(!stage||artCanvas.hidden||!state.photoReady){if(artFx) artFx.hidden=true;if(confirmPromptEl) confirmPromptEl.hidden=true;return;}var stageRect=stage.getBoundingClientRect();var artRect=artCanvas.getBoundingClientRect();if(!stageRect.width||!stageRect.height||!artRect.width||!artRect.height){if(artFx) artFx.hidden=true;if(confirmPromptEl) confirmPromptEl.hidden=true;return;}applyLiveArtworkPhotorealism();if(artFx){artFx.hidden=false;artFx.style.left=(artRect.left-stageRect.left)+'px';artFx.style.top=(artRect.top-stageRect.top)+'px';artFx.style.width=artRect.width+'px';artFx.style.height=artRect.height+'px';}if(confirmPromptEl&&!confirmPromptEl.hidden){var right=clamp(artRect.right-stageRect.left-3,70,stageRect.width-4);var top=clamp(artRect.top-stageRect.top-15,3,stageRect.height-28);confirmPromptEl.style.left=right+'px';confirmPromptEl.style.top=top+'px';}}
function requestArtworkEffectsSync(){window.requestAnimationFrame(syncArtworkEffects);}
function hideConfirmPrompt(){if(confirmTimer){window.clearTimeout(confirmTimer);confirmTimer=0;}if(confirmPromptEl) confirmPromptEl.hidden=true;}
function hidePlacementGuide(){if(placementGuide) placementGuide.hidden=true;if(stage) stage.classList.remove('is-positioning');}
function showPlacementGuide(){if(!stage||!placementGuide||state.confirmed||!state.photoReady||!previewIsReady()||artCanvas.hidden) return;stage.classList.add('is-positioning');placementGuide.hidden=false;requestArtworkEffectsSync();}
function showConfirmPrompt(delay){if(confirmTimer) window.clearTimeout(confirmTimer);if(!state.photoReady||!previewIsReady()||artCanvas.hidden||state.confirmed||state.confirming||!state.hasDraggedPlacement){hideConfirmPrompt();return;}confirmTimer=window.setTimeout(function(){state.confirmPromptReady=true;if(confirmPromptEl){confirmPromptEl.classList.remove('is-confirmed');confirmPromptEl.hidden=false;}if(confirmLabel) confirmLabel.textContent='Place';requestArtworkEffectsSync();},Math.max(0,Number(delay||0)));}
function invalidateConfirmation(showPrompt){if(state.confirming) return;state.confirmed=false;state.hasDraggedPlacement=false;savedBlob=null;assetRevision+=1;assetPromise=null;savedFile=null;archivePromise=null;lastArchiveBlob=null;state.storageSaved=false;state.storageAccepted=false;state.archiveStatus='';root.classList.remove('sc-wall-v1--confirmed');if(overlay) overlay.classList.remove('is-confirmed');stage.classList.remove('is-confirmed');setShareNote('');setPreviewActionState();if(showPrompt!==false&&state.photoReady&&previewIsReady()&&!artCanvas.hidden){showPlacementGuide();showConfirmPrompt(180);}else{hidePlacementGuide();hideConfirmPrompt();}syncSizeAvailabilityFromPicker();}
function markConfirmedUi(){state.confirmed=true;state.hasPlacedOnce=true;state.confirmPromptReady=false;hidePlacementGuide();root.classList.add('sc-wall-v1--confirmed');if(overlay) overlay.classList.add('is-confirmed');stage.classList.add('is-confirmed');if(confirmPromptEl){confirmPromptEl.hidden=false;confirmPromptEl.classList.add('is-confirmed');}if(confirmLabel) confirmLabel.textContent='✓ Your wall preview is ready';setPreviewActionState();requestArtworkEffectsSync();updateStickyBuy();if(confirmTimer) window.clearTimeout(confirmTimer);confirmTimer=window.setTimeout(function(){if(!state.confirmed) return;if(confirmPromptEl) confirmPromptEl.hidden=true;},1800);}
function setUnit(unit){unit=unit==='in'?'in':'cm';state.unit=unit;root.setAttribute('data-unit',unit);if(measurementUnit) measurementUnit.textContent=unit;if(scaleUnitInline) scaleUnitInline.textContent=unit;if(referenceMeasurement) referenceMeasurement.placeholder='';renderSizeButtons();updateStatus();if(state.calibrated&&!state.quickPreview) applyScaledSize();}
function renderSizeButtons(){var order={XL:0,L:1,M:2,S:3};sizeButtons.forEach(function(button,index){var info=parseSizeInfo(button.getAttribute('data-size-raw')||'',Number(button.getAttribute('data-size-index')||index));button.__scSizeInfo=info;button.style.order=Object.prototype.hasOwnProperty.call(order,info.token)?String(order[info.token]):String(10+index);var token=button.querySelector('[data-sc-wall-size-token]');var dims=button.querySelector('[data-sc-wall-size-dims]');if(token) token.textContent=info.token;if(dims) dims.textContent=formatSize(info,state.unit);});}
function getSelectedSizeButton(){return sizeButtons.find(function(btn){return btn.getAttribute('aria-pressed')==='true';})||sizeButtons.find(function(btn){return !btn.disabled;})||sizeButtons[0]||null;}
function clearUpsizeCue(){sizeButtons.forEach(function(btn){btn.classList.remove('is-upsize');var badge=btn.querySelector('[data-sc-wall-upsize-badge]');if(badge) badge.hidden=true;});}
function renderUpsizeCue(){clearUpsizeCue();if(!state.upsizeCueArmed||state.upsizeCueConsumed||!state.upsizeCueTargetRaw) return;var target=sizeButtons.find(function(btn){return clean(btn.getAttribute('data-size-raw')||'')===state.upsizeCueTargetRaw;});if(!target||target.disabled) return;target.classList.add('is-upsize');var badge=target.querySelector('[data-sc-wall-upsize-badge]');if(badge) badge.hidden=false;}
function armOneTimeUpsizeCue(){if(state.upsizeCueArmed||state.upsizeCueConsumed||!state.sizeInfo) return;state.upsizeCueArmed=true;var currentArea=state.sizeInfo.widthCm*state.sizeInfo.heightCm;var larger=sizeButtons.filter(function(btn){if(btn.disabled) return false;var info=btn.__scSizeInfo||parseSizeInfo(btn.getAttribute('data-size-raw')||'',Number(btn.getAttribute('data-size-index')||0));return info.widthCm*info.heightCm>currentArea+.01;}).sort(function(a,b){var ai=a.__scSizeInfo||parseSizeInfo(a.getAttribute('data-size-raw')||'',0);var bi=b.__scSizeInfo||parseSizeInfo(b.getAttribute('data-size-raw')||'',0);return ai.widthCm*ai.heightCm-bi.widthCm*bi.heightCm;});var next=larger[0];state.upsizeCueTargetRaw=next?clean(next.getAttribute('data-size-raw')||''):'';renderUpsizeCue();}
function consumeUpsizeCue(){if(state.upsizeCueConsumed) return;state.upsizeCueConsumed=true;state.upsizeCueTargetRaw='';clearUpsizeCue();}
function selectSizeButton(button,syncPicker,userInitiated){if(!button||button.disabled) return;if(userInitiated) consumeUpsizeCue();var nextRaw=clean(button.getAttribute('data-size-raw')||'');var changed=!!(state.sizeRaw&&state.sizeRaw!==nextRaw);if(changed){savedBlob=null;assetRevision+=1;assetPromise=null;savedFile=null;}var wasConfirmed=state.confirmed;if(wasConfirmed&&!changed) return;if(wasConfirmed&&changed) invalidateConfirmation(false);sizeButtons.forEach(function(btn){btn.setAttribute('aria-pressed',btn===button?'true':'false');});state.sizeRaw=nextRaw;state.sizeInfo=button.__scSizeInfo||parseSizeInfo(state.sizeRaw,Number(button.getAttribute('data-size-index')||0));updateStatus();renderUpsizeCue();if(syncPicker) syncSizeToPicker(state.sizeRaw,state.sizeInfo.token);if(state.quickPreview) applyQuickPreviewSize();else if(state.calibrated) applyScaledSize();if(wasConfirmed&&changed){state.previewChipDismissed=false;updatePreviewChip();showPlacementGuide();showConfirmPrompt(120);setPreviewActionState();updateStickyBuy();}}
function findButtonForRaw(raw){raw=clean(raw);var exact=sizeButtons.find(function(btn){return clean(btn.getAttribute('data-size-raw')||'')===raw;});if(exact) return exact;var parsed=parseSizeInfo(raw,0);return sizeButtons.find(function(btn){var info=btn.__scSizeInfo||parseSizeInfo(btn.getAttribute('data-size-raw')||'',Number(btn.getAttribute('data-size-index')||0));return info.token===parsed.token;})||null;}
function sizeGroupFromPicker(){var picker=productPickerFor(root);if(!picker) return null;var group=null;picker.querySelectorAll('.option-selector').forEach(function(item){var name=String(item.getAttribute('data-option')||'').toLowerCase();if(!group&&name.indexOf('size')>-1) group=item;});return group;}
function syncSizeAvailabilityFromPicker(){var archived=editionArchived();sizeButtons.forEach(function(button){button.disabled=archived;});}
function syncSizeToPicker(raw,token){var group=sizeGroupFromPicker();if(!group) return;var input=Array.prototype.find.call(group.querySelectorAll('input[type="radio"]'),function(item){return clean(item.value)===clean(raw);});if(!input&&token){input=Array.prototype.find.call(group.querySelectorAll('input[type="radio"]'),function(item){return parseSizeInfo(item.value,0).token===token;});}if(!input||input.checked) return;input.checked=true;input.dispatchEvent(new Event('change',{bubbles:true}));}
function syncFromProductPage(skipArtworkDraw){state.frame=currentFrameFromPicker(root);var pageUnit=currentUnitFromPicker(root);if(pageUnit) setUnit(pageUnit);var raw=currentSizeFromPicker(root);var button=raw?findButtonForRaw(raw):null;syncSizeAvailabilityFromPicker();if(button&&!button.disabled) selectSizeButton(button,false,false);else if(!state.sizeInfo) selectSizeButton(getSelectedSizeButton(),false);if(frameLabel) frameLabel.textContent=frameName(state.frame);if(state.photoReady&&!skipArtworkDraw) drawArtwork();updateStatus();}
function updateStatus(){if(frameLabel) frameLabel.textContent=frameName(state.frame);if(sizeSummary) sizeSummary.textContent=state.sizeInfo?state.sizeInfo.token+' • '+formatSize(state.sizeInfo,state.unit):'';}
function updatePreviewChip(){if(!previewChip) return;previewChip.hidden=!(state.photoReady&&state.quickPreview&&!state.calibrationActive&&!state.awaitingMeasurement&&!state.calibrated);}
function drawArtwork(){state.frame=currentFrameFromPicker(root);updateStatus();var crop=CROPS[state.frame]||CROPS.black;var sourceFrame=state.frame==='unframed'?'black':state.frame;var url=sourceUrlFor(sourceFrame);var renderScale=2;artCanvas.width=Math.round(crop.w*renderScale);artCanvas.height=Math.round(crop.h*renderScale);context.clearRect(0,0,artCanvas.width,artCanvas.height);return loadImage(url).then(function(image){state.artworkFailed=false;if(artError)artError.hidden=true;var scaleX=image.naturalWidth/SOURCE_SIZE;var scaleY=image.naturalHeight/SOURCE_SIZE;context.clearRect(0,0,artCanvas.width,artCanvas.height);context.imageSmoothingEnabled=true;context.imageSmoothingQuality='high';context.drawImage(image,crop.x*scaleX,crop.y*scaleY,crop.w*scaleX,crop.h*scaleY,0,0,artCanvas.width,artCanvas.height);requestArtworkEffectsSync();}).catch(function(){state.artworkFailed=true;artCanvas.hidden=true;if(artError)artError.hidden=false;context.clearRect(0,0,artCanvas.width,artCanvas.height);setPreviewActionState();requestArtworkEffectsSync();});}
function applyArtworkPosition(){artCanvas.style.left=state.centerX+'%';artCanvas.style.top=state.centerY+'%';requestArtworkEffectsSync();}
function resetArtworkPosition(){state.centerX=50;state.centerY=44;applyArtworkPosition();}
function calibrationDistancePx(){if(!state.pointA||!state.pointB) return 0;var rect=stage.getBoundingClientRect();if(!rect.width||!rect.height) return 0;var dx=((state.pointB.x-state.pointA.x)/100)*rect.width;var dy=((state.pointB.y-state.pointA.y)/100)*rect.height;return Math.sqrt(dx*dx+dy*dy);}
function applyScaledSize(){if(!state.calibrated||!state.sizeInfo||!state.referenceMeasurement) return;var rect=stage.getBoundingClientRect();var refPx=calibrationDistancePx();if(!rect.width||!refPx) return;var artWidth=state.unit==='in'?state.sizeInfo.widthIn:state.sizeInfo.widthCm;var artPx=artWidth*(refPx/state.referenceMeasurement);state.artWidthPercent=clamp((artPx/rect.width)*100,3,500);artCanvas.style.width=state.artWidthPercent.toFixed(3)+'%';artCanvas.hidden=!!state.artworkFailed;setPreviewActionState();updatePreviewChip();requestArtworkEffectsSync();if(!state.confirmed){showPlacementGuide();showConfirmPrompt(550);}updateStickyBuy();window.setTimeout(primePreviewActionAsset,30);}
function positionMeasurementVisuals(){if(!state.calibrationActive&&!state.awaitingMeasurement){if(pointAEl) pointAEl.hidden=true;if(pointBEl) pointBEl.hidden=true;if(measureLine) measureLine.hidden=true;return;}if(state.pointA&&pointAEl){pointAEl.hidden=false;pointAEl.style.left=state.pointA.x+'%';pointAEl.style.top=state.pointA.y+'%';}else if(pointAEl){pointAEl.hidden=true;}if(state.pointB&&pointBEl){pointBEl.hidden=false;pointBEl.style.left=state.pointB.x+'%';pointBEl.style.top=state.pointB.y+'%';}else if(pointBEl){pointBEl.hidden=true;}if(!measureLine||!state.pointA||!state.pointB){if(measureLine) measureLine.hidden=true;return;}var rect=stage.getBoundingClientRect();var x1=state.pointA.x/100*rect.width;var y1=state.pointA.y/100*rect.height;var x2=state.pointB.x/100*rect.width;var y2=state.pointB.y/100*rect.height;var dx=x2-x1,dy=y2-y1;var distance=Math.sqrt(dx*dx+dy*dy);var angle=Math.atan2(dy,dx)*180/Math.PI;measureLine.hidden=false;measureLine.style.left=state.pointA.x+'%';measureLine.style.top=state.pointA.y+'%';measureLine.style.width=distance+'px';measureLine.style.transform='translateY(-50%) rotate('+angle+'deg)';}
function hideQuickBadge(){if(quickBadge) quickBadge.hidden=true;}
function hideScaleHelp(){if(scaleHelp) scaleHelp.hidden=true;if(scaleHelpReopen) scaleHelpReopen.hidden=true;if(tapDemo) tapDemo.hidden=true;setFlowError('');syncLandscapeScaleDock();}
function renderScaleHelp(){
if(!scaleHelp) return;
var active=state.photoReady&&!state.quickPreview&&!state.calibrated&&(state.calibrationActive||state.awaitingMeasurement);
if(!active){hideScaleHelp();return;}
var isMeasure=state.awaitingMeasurement;
var hasFirst=!!state.pointA&&!state.pointB&&!isMeasure;
if(tapDemo) tapDemo.hidden=!(state.calibrationActive&&!state.pointA);
if(state.scaleHelpDismissed){scaleHelp.hidden=true;if(scaleHelpReopen) scaleHelpReopen.hidden=false;return;}
scaleHelp.hidden=false;if(scaleHelpReopen) scaleHelpReopen.hidden=true;
if(scaleHelp) scaleHelp.classList.toggle('is-measure',isMeasure);if(scaleHelpTitle) scaleHelpTitle.textContent=isMeasure?'Enter the distance':(hasFirst?'Tap the other side':'Get the real size');
if(scaleCopyStart) scaleCopyStart.hidden=isMeasure||hasFirst;
if(scaleCopySecond) scaleCopySecond.hidden=!hasFirst;
if(scaleCopyMeasure) scaleCopyMeasure.hidden=!isMeasure;
if(scaleEntry) scaleEntry.hidden=!isMeasure;
if(tapInstruction) tapInstruction.hidden=true;
syncLandscapeScaleDock();
}
function closeScaleHelp(){state.scaleHelpDismissed=true;renderScaleHelp();if(tapInstruction&&state.calibrationActive){tapInstruction.textContent=state.pointA?'Tap the other end':'Tap one end';tapInstruction.hidden=false;}}
function reopenScaleHelp(){state.scaleHelpDismissed=false;renderScaleHelp();if(tapInstruction) tapInstruction.hidden=true;}
function clearCalibration(hideArtwork){state.calibrated=false;state.quickPreview=false;state.hasDraggedPlacement=false;state.calibrationActive=false;state.awaitingMeasurement=false;state.referenceMeasurement=0;state.pointA=null;state.pointB=null;state.scaleHelpDismissed=false;stage.classList.remove('is-calibrating');positionMeasurementVisuals();if(tapInstruction) tapInstruction.hidden=true;if(hideArtwork) artCanvas.hidden=true;if(artFx&&hideArtwork) artFx.hidden=true;if(previewChip) previewChip.hidden=true;if(resetButton) resetButton.hidden=true;if(referenceMeasurement) referenceMeasurement.value='';hideQuickBadge();hideScaleHelp();state.confirmed=false;savedBlob=null;assetRevision+=1;assetPromise=null;savedFile=null;archivePromise=null;lastArchiveBlob=null;hideConfirmPrompt();setPreviewActionState();requestArtworkEffectsSync();}
function showMeasureIntro(){clearCalibration(true);startPointSelection();}
function startPointSelection(){state.calibrated=false;state.quickPreview=false;state.calibrationActive=true;state.awaitingMeasurement=false;state.referenceMeasurement=0;state.pointA=null;state.pointB=null;state.scaleHelpDismissed=false;hideQuickBadge();if(previewChip) previewChip.hidden=true;if(resetButton) resetButton.hidden=false;hidePlacementGuide();hideConfirmPrompt();artCanvas.hidden=true;if(artFx) artFx.hidden=true;stage.classList.add('is-calibrating');positionMeasurementVisuals();requestArtworkEffectsSync();if(tapInstruction) tapInstruction.hidden=true;renderScaleHelp();setPreviewActionState();updateStickyBuy();}
function showMeasurementStep(){var distance=calibrationDistancePx();if(distance<12){state.pointA=null;state.pointB=null;positionMeasurementVisuals();if(state.scaleHelpDismissed&&tapInstruction){tapInstruction.textContent='Try again — tap one end';tapInstruction.hidden=false;}renderScaleHelp();return;}state.calibrationActive=false;state.awaitingMeasurement=true;state.scaleHelpDismissed=false;stage.classList.remove('is-calibrating');positionMeasurementVisuals();if(tapInstruction) tapInstruction.hidden=true;renderScaleHelp();if(referenceMeasurement){referenceMeasurement.value='';window.requestAnimationFrame(function(){window.setTimeout(function(){try{referenceMeasurement.focus({preventScroll:true});}catch(error){try{referenceMeasurement.focus();}catch(innerError){}}},90);});}}
function submitMeasurement(){var raw=referenceMeasurement?String(referenceMeasurement.value||'').trim().replace(',','.').replace(/[^0-9.]/g,''):'';var amount=Number(raw);if(!Number.isFinite(amount)||amount<=0){setFlowError('Enter the distance between your two points.');if(referenceMeasurement){try{referenceMeasurement.focus({preventScroll:true});referenceMeasurement.select();}catch(error){referenceMeasurement.focus();}}return;}if(referenceMeasurement) referenceMeasurement.value=String(raw);setFlowError('');state.referenceMeasurement=amount;state.awaitingMeasurement=false;state.quickPreview=false;state.hasDraggedPlacement=false;state.calibrated=true;hideQuickBadge();if(previewChip) previewChip.hidden=true;if(resetButton) resetButton.hidden=false;hideScaleHelp();positionMeasurementVisuals();drawArtwork().then(function(){applyScaledSize();window.requestAnimationFrame(syncDesktopPreviewLayout);});}
function quickPreviewLargestWidth(){var largest=0;sizeButtons.forEach(function(button,index){if(button.disabled) return;var info=button.__scSizeInfo||parseSizeInfo(button.getAttribute('data-size-raw')||'',Number(button.getAttribute('data-size-index')||index));if(info&&Number.isFinite(info.widthCm)) largest=Math.max(largest,info.widthCm);});return largest||87;}
function applyQuickPreviewSize(){if(!state.quickPreview||!state.sizeInfo) return;var largest=quickPreviewLargestWidth();var ratio=largest>0?state.sizeInfo.widthCm/largest:1;var quickBase=82,quickMin=22;if(state.photoLandscape){var photoRatio=roomImage.naturalWidth&&roomImage.naturalHeight?roomImage.naturalWidth/roomImage.naturalHeight:1.7778;var artRatio=artCanvas.width&&artCanvas.height?artCanvas.width/artCanvas.height:1.344;var heightSafeBase=(78*artRatio)/Math.max(1.05,photoRatio);quickBase=clamp(Math.min(62,heightSafeBase),34,62);quickMin=15;}state.artWidthPercent=clamp(quickBase*ratio,quickMin,quickBase);artCanvas.style.width=state.artWidthPercent.toFixed(2)+'%';artCanvas.hidden=!!state.artworkFailed;setPreviewActionState();updatePreviewChip();requestArtworkEffectsSync();if(!state.confirmed) showConfirmPrompt(180);updateStickyBuy();window.setTimeout(primePreviewActionAsset,30);}
function showQuickPreview(reuseRenderedArtwork){state.calibrated=false;state.quickPreview=true;state.hasDraggedPlacement=false;state.calibrationActive=false;state.awaitingMeasurement=false;state.referenceMeasurement=0;state.pointA=null;state.pointB=null;stage.classList.remove('is-calibrating');hideScaleHelp();if(resetButton) resetButton.hidden=true;if(quickBadge) quickBadge.hidden=false;positionMeasurementVisuals();if(tapInstruction) tapInstruction.hidden=true;state.confirmed=false;savedBlob=null;assetRevision+=1;assetPromise=null;savedFile=null;archivePromise=null;lastArchiveBlob=null;root.classList.remove('sc-wall-v1--confirmed');if(overlay) overlay.classList.remove('is-confirmed');stage.classList.remove('is-confirmed');hideConfirmPrompt();var finishQuickPreview=function(){applyQuickPreviewSize();updatePreviewChip();showPlacementGuide();showConfirmPrompt(350);window.requestAnimationFrame(syncDesktopPreviewLayout);};if(reuseRenderedArtwork&&artCanvas.width>0&&artCanvas.height>0&&!artCanvas.hidden){finishQuickPreview();return;}drawArtwork().then(finishQuickPreview);}
function setTrueScaleFromQuick(){state.quickPreview=false;hideQuickBadge();invalidateConfirmation(false);startPointSelection();}
function stageCalibrationTap(event){if(!state.calibrationActive) return;if(event.button!==undefined&&event.button!==0) return;event.preventDefault();var rect=stage.getBoundingClientRect();if(!rect.width||!rect.height) return;var point={x:clamp((event.clientX-rect.left)/rect.width*100,0,100),y:clamp((event.clientY-rect.top)/rect.height*100,0,100)};if(!state.pointA){state.pointA=point;positionMeasurementVisuals();if(state.scaleHelpDismissed&&tapInstruction){tapInstruction.textContent='Tap the other end';tapInstruction.hidden=false;}renderScaleHelp();}else{state.pointB=point;positionMeasurementVisuals();showMeasurementStep();}}
function scrollVisualizerTop(){if(!modal) return;modal.scrollTop=0;if(typeof modal.scrollTo==='function'){try{modal.scrollTo({top:0,left:0,behavior:'auto'});}catch(error){modal.scrollTop=0;}}window.requestAnimationFrame(function(){modal.scrollTop=0;updateStickyBuy();});}
function desktopPreviewMode(){return Math.max(1,window.innerWidth||document.documentElement.clientWidth||1)>=841||window.matchMedia('(orientation:landscape) and (max-height:500px)').matches;}
function clearDesktopPreviewLayout(){[dialog,modal,stageWrap,stage].forEach(function(node){if(!node) return;node.style.removeProperty('width');node.style.removeProperty('height');node.style.removeProperty('max-width');node.style.removeProperty('max-height');node.style.removeProperty('min-height');});}
function syncDesktopPreviewLayout(){
if(!stageWrap||!desktopPreviewMode()||!state.photoReady||overlay.hidden||!roomImage.naturalWidth||!roomImage.naturalHeight){clearDesktopPreviewLayout();return;}
var viewportW=Math.max(1,window.innerWidth||document.documentElement.clientWidth||1280);
var viewportH=Math.max(1,window.visualViewport?window.visualViewport.height:(window.innerHeight||document.documentElement.clientHeight||800));
var photoRatio=roomImage.naturalWidth/roomImage.naturalHeight;
var scalePending=!!(state.calibrationActive||state.awaitingMeasurement);
var landscapePhoto=!!state.photoLandscape;
var maxDialogW=Math.max(520,Math.min(landscapePhoto?1420:760,viewportW-16));
var dialogPad=12;
var utilityH=retakeButton&&retakeButton.parentNode&&!retakeButton.parentNode.hidden?38:0;
var shareH=shareNote&&clean(shareNote.textContent)?18:0;
var dockH=(landscapeScaleDock&&!landscapeScaleDock.hidden&&landscapeScaleDock.classList.contains('is-active'))?Math.max(0,landscapeScaleDock.getBoundingClientRect().height+6):0;
var stickyH=(!scalePending&&stickyBuy&&!stickyBuy.hidden)?Math.max(0,stickyBuy.getBoundingClientRect().height+12):0;
if(!stickyH&&!scalePending) stickyH=landscapePhoto?64:104;
var chromeH=dialogPad+utilityH+shareH+dockH+stickyH+10;
var maxDialogH=Math.max(1,viewportH-16);
var maxStageH=Math.max(1,maxDialogH-chromeH);
var maxStageW=Math.max(320,maxDialogW-12);
var stageW=Math.min(maxStageW,maxStageH*photoRatio);
var stageH=stageW/photoRatio;
if(stageH>maxStageH){stageH=maxStageH;stageW=stageH*photoRatio;}
var minDialogW=landscapePhoto?760:Math.min(620,viewportW-16);
var dialogW=Math.min(viewportW-16,Math.max(minDialogW,stageW+12));
var dialogH=Math.min(maxDialogH,Math.max(360,stageH+chromeH));
dialog.style.setProperty('width',Math.round(dialogW)+'px','important');
dialog.style.setProperty('max-width',Math.round(dialogW)+'px','important');
dialog.style.setProperty('height',Math.round(dialogH)+'px','important');
dialog.style.setProperty('max-height',Math.round(dialogH)+'px','important');
modal.style.setProperty('height','100%','important');
modal.style.setProperty('max-height','100%','important');
stageWrap.style.setProperty('width',Math.round(stageW+10)+'px','important');
stageWrap.style.setProperty('max-width',Math.round(stageW+10)+'px','important');
stage.style.setProperty('width',Math.round(stageW)+'px','important');
stage.style.setProperty('height',Math.round(stageH)+'px','important');
stage.style.setProperty('min-height','0','important');
requestArtworkEffectsSync();
}
function activatePhoto(file,fromCameraTransition,desktopFallbackTried){
if(!isImageUploadFile(file)) return;
var preserveInstantCameraState=!!(fromCameraTransition&&captureTransitionPending&&state.photoReady&&state.quickPreview&&captureFreezeCanvas);
if(!fromCameraTransition) setPhotoLandscapeLayout(false);
scrollVisualizerTop();
var loadSeq=++photoLoadSeq;
if(objectUrl) URL.revokeObjectURL(objectUrl);
objectUrl=URL.createObjectURL(file);
savedBlob=null;assetRevision+=1;assetPromise=null;
savedFile=null;
archivePromise=null;
lastArchiveBlob=null;
state.previewId='';
state.shareUrl='';
state.storageSaved=false;state.storageAccepted=false;state.archiveStatus='';
state.clientPreviewId=makeId('preview');
if(!preserveInstantCameraState){
state.confirmed=false;
state.confirming=false;
state.hasDraggedPlacement=false;
state.quickPreview=false;
state.hasPlacedOnce=false;
}
state.startedAt=new Date().toISOString();
if(saveWrap) saveWrap.hidden=true;
if(saveButton) saveButton.disabled=true;
if(saveLabel) saveLabel.textContent='Download Your Preview';
if(sharePreviewButton) sharePreviewButton.disabled=true;
setSharePreviewLabel('Share Preview');
if(!preserveInstantCameraState){
root.classList.remove('sc-wall-v1--confirmed');
if(overlay) overlay.classList.remove('is-confirmed');
stage.classList.remove('is-confirmed');
hidePlacementGuide();
hideConfirmPrompt();
}

roomImage.onload=function(){
if(loadSeq!==photoLoadSeq) return;
roomImage.onerror=null;
var ratio=roomImage.naturalWidth&&roomImage.naturalHeight?roomImage.naturalWidth/roomImage.naturalHeight:4/3;
stage.style.aspectRatio=String(ratio);
setPhotoLandscapeLayout(ratio>1.05);
clearCaptureFreeze();
captureTransitionPending=false;
roomImage.style.visibility='';
intro.hidden=true;
editor.hidden=false;
state.photoReady=true;
setStagePhotoState();

state.previewChipDismissed=false;
syncFromProductPage(true);
if(preserveInstantCameraState){
if(state.quickPreview) applyQuickPreviewSize();
applyArtworkPosition();
updatePreviewChip();
if(!state.confirmed){
if(state.hasDraggedPlacement) showConfirmPrompt(40);
else showPlacementGuide();
}
setPreviewActionState();
updateStickyBuy();
if(state.confirmed&&!state.storageSaved) window.setTimeout(startPlacementPersistenceInBackground,0);
}else{
resetArtworkPosition();
showQuickPreview(!!fromCameraTransition);
}
scrollVisualizerTop();
window.requestAnimationFrame(function(){positionMeasurementVisuals();requestArtworkEffectsSync();syncDesktopPreviewLayout();scrollVisualizerTop();});
setShareNote('');
updateStickyBuy();
window.requestAnimationFrame(syncDesktopPreviewLayout);
};

roomImage.onerror=function(){
if(loadSeq!==photoLoadSeq) return;

/* Desktop-only safety net:
If Chrome/Edge cannot display the original file directly (common with some
large/wide landscape photos, unusual JPEG encodings, or files with missing
MIME metadata), decode it once into a browser-safe image and retry.
Mobile/camera behavior is intentionally untouched. */
if(!state.isMobileCamera&&!desktopFallbackTried){
roomImage.onload=null;
roomImage.onerror=null;
normalizeDesktopUploadFallback(file).then(function(normalizedFile){
if(loadSeq!==photoLoadSeq) return;
activatePhoto(normalizedFile,fromCameraTransition,true);
}).catch(function(){
if(loadSeq!==photoLoadSeq) return;
captureTransitionPending=false;
clearCaptureFreeze();
roomImage.style.visibility='';
state.photoReady=false;
setPhotoLandscapeLayout(false);
setStagePhotoState();
editor.hidden=true;
intro.hidden=false;
if(deviceNote){deviceNote.textContent='Could not open that image. Try another photo.';deviceNote.hidden=false;}
updateStickyBuy();
});
return;
}

captureTransitionPending=false;
clearCaptureFreeze();
roomImage.style.visibility='';
state.photoReady=false;
setPhotoLandscapeLayout(false);
setStagePhotoState();
editor.hidden=true;
intro.hidden=false;
if(deviceNote){deviceNote.textContent='Could not open that image. Try another photo.';deviceNote.hidden=false;}
updateStickyBuy();
};

roomImage.src=objectUrl;
}
function cameraTouchDistance(touches){if(!touches||touches.length<2) return 0;var dx=touches[0].clientX-touches[1].clientX;var dy=touches[0].clientY-touches[1].clientY;return Math.sqrt(dx*dx+dy*dy);}
function configureCameraZoom(){cameraTrack=cameraStream&&cameraStream.getVideoTracks?cameraStream.getVideoTracks()[0]:null;cameraNativeZoom=false;cameraZoomMin=1;cameraZoomMax=3;cameraZoomValue=1;if(cameraTrack&&typeof cameraTrack.getCapabilities==='function'){try{var capabilities=cameraTrack.getCapabilities()||{};if(capabilities.zoom&&Number.isFinite(capabilities.zoom.min)&&Number.isFinite(capabilities.zoom.max)){cameraNativeZoom=true;cameraZoomMin=Number(capabilities.zoom.min);cameraZoomMax=Math.min(Number(capabilities.zoom.max),5);var settings=typeof cameraTrack.getSettings==='function'?cameraTrack.getSettings():{};cameraZoomValue=Number.isFinite(settings.zoom)?clamp(Number(settings.zoom),cameraZoomMin,cameraZoomMax):cameraZoomMin;}}catch(error){cameraNativeZoom=false;}}if(!cameraNativeZoom){cameraZoomMin=1;cameraZoomMax=3;cameraZoomValue=1;}cameraPendingZoom=cameraZoomValue;if(cameraVideo){cameraVideo.style.transform=cameraNativeZoom?'scale(1)':'scale('+cameraZoomValue+')';cameraVideo.style.transformOrigin='50% 50%';}}
async function applyBestCameraImageSettings(){if(!cameraTrack||typeof cameraTrack.getCapabilities!=='function'||typeof cameraTrack.applyConstraints!=='function') return;try{var caps=cameraTrack.getCapabilities()||{};var advanced={};if(Array.isArray(caps.focusMode)&&caps.focusMode.indexOf('continuous')>-1) advanced.focusMode='continuous';if(Array.isArray(caps.exposureMode)&&caps.exposureMode.indexOf('continuous')>-1) advanced.exposureMode='continuous';if(Array.isArray(caps.whiteBalanceMode)&&caps.whiteBalanceMode.indexOf('continuous')>-1) advanced.whiteBalanceMode='continuous';if(caps.exposureCompensation&&Number.isFinite(caps.exposureCompensation.min)&&Number.isFinite(caps.exposureCompensation.max)){advanced.exposureCompensation=clamp(0.25,Number(caps.exposureCompensation.min),Number(caps.exposureCompensation.max));}if(Object.keys(advanced).length){await cameraTrack.applyConstraints({advanced:[advanced]});}}catch(error){}}
async function setCameraZoom(next){next=clamp(Number(next)||cameraZoomMin,cameraZoomMin,cameraZoomMax);cameraZoomValue=next;if(cameraNativeZoom&&cameraTrack&&typeof cameraTrack.applyConstraints==='function'){try{await cameraTrack.applyConstraints({advanced:[{zoom:cameraZoomValue}]});var settings=typeof cameraTrack.getSettings==='function'?cameraTrack.getSettings():{};if(Number.isFinite(settings.zoom)) cameraZoomValue=Number(settings.zoom);if(cameraVideo) cameraVideo.style.transform='scale(1)';return;}catch(error){cameraNativeZoom=false;cameraZoomMin=1;cameraZoomMax=3;cameraZoomValue=clamp(next,1,3);}}if(cameraVideo){cameraVideo.style.transform='scale('+cameraZoomValue+')';cameraVideo.style.transformOrigin='50% 50%';}}
function beginCameraPinch(event){if(!cameraVideo||!cameraStream||!event.touches||event.touches.length!==2) return;cameraPinchStartDistance=cameraTouchDistance(event.touches);cameraPinchStartZoom=cameraZoomValue;if(cameraPinchStartDistance>0) event.preventDefault();}
function moveCameraPinch(event){if(!cameraVideo||!cameraStream||!event.touches||event.touches.length!==2||!cameraPinchStartDistance) return;event.preventDefault();var distance=cameraTouchDistance(event.touches);if(!distance) return;cameraPendingZoom=clamp(cameraPinchStartZoom*(distance/cameraPinchStartDistance),cameraZoomMin,cameraZoomMax);if(cameraZoomRaf) return;cameraZoomRaf=window.requestAnimationFrame(function(){cameraZoomRaf=0;setCameraZoom(cameraPendingZoom);});}
function endCameraPinch(event){if(!event.touches||event.touches.length<2){cameraPinchStartDistance=0;cameraPinchStartZoom=cameraZoomValue;}}
function cameraFullscreenElement(){return document.fullscreenElement||document.webkitFullscreenElement||null;}
function requestCameraFullscreen(){
if(!liveCamera||cameraFullscreenElement()) return;
try{
if(typeof liveCamera.requestFullscreen==='function'){
var requestResult;
try{requestResult=liveCamera.requestFullscreen({navigationUI:'hide'});}catch(firstError){requestResult=liveCamera.requestFullscreen();}
if(requestResult&&typeof requestResult.catch==='function') requestResult.catch(function(){});
}else if(typeof liveCamera.webkitRequestFullscreen==='function'){
liveCamera.webkitRequestFullscreen();
}
}catch(error){}
}
function exitCameraFullscreen(){
var active=cameraFullscreenElement();
if(!active||!(active===liveCamera||(liveCamera&&liveCamera.contains&&liveCamera.contains(active)))) return;
try{
var result=null;
if(typeof document.exitFullscreen==='function') result=document.exitFullscreen();
else if(typeof document.webkitExitFullscreen==='function') result=document.webkitExitFullscreen();
if(result&&typeof result.catch==='function') result.catch(function(){});
}catch(error){}
}
function cameraVisibleRatio(){
var rect=cameraShell&&cameraShell.getBoundingClientRect?cameraShell.getBoundingClientRect():null;
if(rect&&rect.width>1&&rect.height>1) return rect.width/rect.height;
var viewportW=Math.max(1,window.innerWidth||document.documentElement.clientWidth||1),viewportH=Math.max(1,window.innerHeight||document.documentElement.clientHeight||1);
return viewportW/viewportH;
}
function cameraTargetRatio(){
var visible=cameraVisibleRatio();
if(viewportIsLandscape()) return visible>1?visible:(16/9);
return visible>0?visible:((window.innerWidth||1)/(window.innerHeight||1));
}
function cameraCropRect(sourceW,sourceH){var targetRatio=cameraTargetRatio();var cropW=sourceW,cropH=sourceH;if(sourceW/sourceH>targetRatio){cropW=sourceH*targetRatio;}else{cropH=sourceW/targetRatio;}var digitalZoom=cameraNativeZoom?1:Math.max(1,cameraZoomValue);cropW/=digitalZoom;cropH/=digitalZoom;return {x:(sourceW-cropW)/2,y:(sourceH-cropH)/2,w:cropW,h:cropH};}
function freezeVisibleCameraFrame(){if(!cameraVideo||!cameraVideo.videoWidth||!cameraVideo.videoHeight) return null;try{var crop=cameraCropRect(cameraVideo.videoWidth,cameraVideo.videoHeight);var canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(crop.w));canvas.height=Math.max(1,Math.round(crop.h));var ctx=canvas.getContext('2d');if(!ctx) return null;ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(cameraVideo,crop.x,crop.y,crop.w,crop.h,0,0,canvas.width,canvas.height);return canvas;}catch(error){return null;}}
function cameraAutoEnhanceFilter(source,crop){var fallback='brightness(1.07) contrast(1.025) saturate(1.055)';try{var sample=document.createElement('canvas');sample.width=48;sample.height=48;var sampleCtx=sample.getContext('2d',{willReadFrequently:true});if(!sampleCtx) return fallback;sampleCtx.drawImage(source,crop.x,crop.y,crop.w,crop.h,0,0,48,48);var pixels=sampleCtx.getImageData(0,0,48,48).data;var total=0,count=0;for(var i=0;i<pixels.length;i+=4){if(pixels[i+3]<16) continue;var luma=.2126*pixels[i]+.7152*pixels[i+1]+.0722*pixels[i+2];if(luma<5||luma>250) continue;total+=luma;count+=1;}var average=count?total/count:135;var brightness=average<82?1.14:(average<108?1.11:(average<138?1.085:(average<170?1.06:1.035)));var contrast=average<105?1.04:(average<155?1.03:1.02);var saturation=average<95?1.065:1.055;return 'brightness('+brightness.toFixed(3)+') contrast('+contrast.toFixed(3)+') saturate('+saturation.toFixed(3)+')';}catch(error){return fallback;}}
function renderCameraSourceToBlob(source,sourceW,sourceH,alreadyCropped){return new Promise(function(resolve,reject){try{var crop=alreadyCropped?{x:0,y:0,w:sourceW,h:sourceH}:cameraCropRect(sourceW,sourceH);var maxDim=3840,maxPixels=12000000;var outScale=Math.min(1,maxDim/crop.w,maxDim/crop.h,Math.sqrt(maxPixels/(crop.w*crop.h)));var capture=document.createElement('canvas');capture.width=Math.max(1,Math.round(crop.w*outScale));capture.height=Math.max(1,Math.round(crop.h*outScale));var captureContext=capture.getContext('2d');if(!captureContext){reject(new Error('Camera canvas unavailable'));return;}captureContext.imageSmoothingEnabled=true;captureContext.imageSmoothingQuality='high';captureContext.filter=cameraAutoEnhanceFilter(source,crop);captureContext.drawImage(source,crop.x,crop.y,crop.w,crop.h,0,0,capture.width,capture.height);captureContext.filter='none';capture.toBlob(function(blob){if(blob) resolve(blob);else reject(new Error('Camera image unavailable'));},'image/jpeg',.97);}catch(error){reject(error);}});}
async function drawableFromCameraBlob(blob){if(!blob) throw new Error('No camera image');if(typeof createImageBitmap==='function'){try{var oriented=await createImageBitmap(blob,{imageOrientation:'from-image'});return {source:oriented,width:oriented.width,height:oriented.height,cleanup:function(){try{oriented.close();}catch(error){}}};}catch(firstError){try{var bitmap=await createImageBitmap(blob);return {source:bitmap,width:bitmap.width,height:bitmap.height,cleanup:function(){try{bitmap.close();}catch(error){}}};}catch(secondError){}}}return new Promise(function(resolve,reject){var url=URL.createObjectURL(blob);var image=new Image();image.onload=function(){resolve({source:image,width:image.naturalWidth,height:image.naturalHeight,cleanup:function(){URL.revokeObjectURL(url);}});};image.onerror=function(){URL.revokeObjectURL(url);reject(new Error('Could not decode camera photo'));};image.src=url;});}
async function highQualityCameraBlob(){if(!cameraVideo||!cameraVideo.videoWidth||!cameraVideo.videoHeight) throw new Error('Camera is not ready');if(cameraImageCapture&&typeof cameraImageCapture.takePhoto==='function'){try{var stillBlob=await cameraImageCapture.takePhoto();var drawable=await drawableFromCameraBlob(stillBlob);try{return await renderCameraSourceToBlob(drawable.source,drawable.width,drawable.height);}finally{drawable.cleanup();}}catch(error){}}return renderCameraSourceToBlob(cameraVideo,cameraVideo.videoWidth,cameraVideo.videoHeight);}
function clearCaptureFreeze(){if(captureFreezeCanvas&&captureFreezeCanvas.parentNode){try{captureFreezeCanvas.parentNode.removeChild(captureFreezeCanvas);}catch(error){}}captureFreezeCanvas=null;}
function primeCameraArtwork(){if(!state.isMobileCamera) return;syncFromProductPage(true);artCanvas.hidden=true;cameraArtworkPrimePromise=drawArtwork().catch(function(){return null;});}
function showInstantCameraArtwork(){if(!captureTransitionPending||!captureFreezeCanvas||!state.sizeInfo)return;var reveal=function(){if(!captureTransitionPending||!captureFreezeCanvas||!state.sizeInfo||!artCanvas.width||!artCanvas.height)return;var largest=quickPreviewLargestWidth(),sizeRatio=largest>0?state.sizeInfo.widthCm/largest:1,quickBase=82,quickMin=22;if(state.photoLandscape){var photoRatio=captureFreezeCanvas.width&&captureFreezeCanvas.height?captureFreezeCanvas.width/captureFreezeCanvas.height:1.7778,artRatio=artCanvas.width&&artCanvas.height?artCanvas.width/artCanvas.height:1.344,heightSafeBase=(78*artRatio)/Math.max(1.05,photoRatio);quickBase=clamp(Math.min(62,heightSafeBase),34,62);quickMin=15;}state.artWidthPercent=clamp(quickBase*sizeRatio,quickMin,quickBase);artCanvas.style.width=state.artWidthPercent.toFixed(2)+'%';artCanvas.style.pointerEvents='auto';artCanvas.style.touchAction='none';resetArtworkPosition();artCanvas.hidden=!!state.artworkFailed;positionMeasurementVisuals();setStagePhotoState();updatePreviewChip();hideConfirmPrompt();showPlacementGuide();setPreviewActionState();updateStickyBuy();requestArtworkEffectsSync();window.requestAnimationFrame(function(){setPreviewActionState();updateStickyBuy();positionMeasurementVisuals();requestArtworkEffectsSync();});};if(cameraArtworkPrimePromise)Promise.resolve(cameraArtworkPrimePromise).then(reveal);else{cameraArtworkPrimePromise=drawArtwork().catch(function(){return null;});Promise.resolve(cameraArtworkPrimePromise).then(reveal);}}
function showCaptureFreeze(canvas){if(!canvas)return;clearCaptureFreeze();captureTransitionPending=true;var ratio=canvas.width&&canvas.height?canvas.width/canvas.height:4/3;stage.style.aspectRatio=String(ratio);state.photoLandscape=ratio>1.05;state.photoReady=true;state.quickPreview=true;state.calibrated=false;state.calibrationActive=false;state.awaitingMeasurement=false;state.referenceMeasurement=0;state.pointA=null;state.pointB=null;state.confirmed=false;state.confirming=false;state.hasDraggedPlacement=false;root.classList.toggle('sc-wall-v1--landscape-photo',state.photoLandscape);root.classList.remove('sc-wall-v1--confirmed');if(overlay){overlay.classList.toggle('is-landscape-photo',state.photoLandscape);overlay.classList.add('is-photo-ready');overlay.classList.remove('is-confirmed');}canvas.className='sc-wall-v1__room sc-wall-v1__capture-freeze';canvas.setAttribute('aria-hidden','true');canvas.style.pointerEvents='none';captureFreezeCanvas=canvas;roomImage.style.visibility='hidden';stage.insertBefore(canvas,stage.firstChild);stage.classList.add('has-photo');stage.classList.remove('is-calibrating','is-confirmed');if(stageTone)stageTone.hidden=false;intro.hidden=true;editor.hidden=false;if(liveCamera)liveCamera.hidden=true;if(quickBadge)quickBadge.hidden=false;if(resetButton)resetButton.hidden=true;if(tapInstruction)tapInstruction.hidden=true;positionMeasurementVisuals();setStagePhotoState();setStickyCartState();setPreviewActionState();updatePreviewChip();updateStickyBuy();showInstantCameraArtwork();window.requestAnimationFrame(function(){setPreviewActionState();updateStickyBuy();syncDesktopPreviewLayout();scrollVisualizerTop();});}
function returnToPhotoStart(){
closeDownloadGate();
captureTransitionPending=false;
cameraArtworkPrimePromise=null;
cameraCaptureSeq+=1;
clearCaptureFreeze();
roomImage.style.visibility='';
stopLiveCamera();
photoLoadSeq+=1;
if(objectUrl){try{URL.revokeObjectURL(objectUrl);}catch(error){}objectUrl='';}
roomImage.onload=null;
roomImage.onerror=null;
roomImage.removeAttribute('src');
clearCalibration(true);
state.photoReady=false;
setPhotoLandscapeLayout(false);
if(desktopPreviewMode()) clearDesktopPreviewLayout();

root.classList.remove('sc-wall-v1--rotate-required');
state.confirmed=false;
state.confirming=false;
state.hasDraggedPlacement=false;
state.quickPreview=false;
state.previewId='';
state.shareUrl='';
state.storageSaved=false;state.storageAccepted=false;state.archiveStatus='';

state.hasPlacedOnce=false;
state.clientPreviewId=makeId('preview');
state.previewChipDismissed=false;
savedBlob=null;assetRevision+=1;assetPromise=null;
savedFile=null;
archivePromise=null;
lastArchiveBlob=null;
root.classList.remove('sc-wall-v1--confirmed');
if(overlay) overlay.classList.remove('is-confirmed','is-photo-ready');
stage.classList.remove('is-confirmed','is-positioning','is-calibrating');
setStagePhotoState();
hidePlacementGuide();
hideConfirmPrompt();
hideScaleHelp();
hideQuickBadge();
if(previewChip) previewChip.hidden=true;
if(saveWrap) saveWrap.hidden=true;

if(sharePreviewButton) sharePreviewButton.disabled=true;
setSharePreviewLabel('Share Preview');



setShareNote('');
editor.hidden=true;
intro.hidden=false;
if(liveCamera) liveCamera.hidden=true;
if(stickyBuy) stickyBuy.hidden=true;
if(modal) modal.classList.remove('has-sticky-buy');
applyDeviceMode();
scrollVisualizerTop();
updateStickyBuy();
}
function syncLiveCameraViewport(){if(!liveCamera||liveCamera.hidden)return;if(cameraViewportRaf)return;cameraViewportRaf=window.requestAnimationFrame(function(){cameraViewportRaf=0;if(!liveCamera||liveCamera.hidden)return;var fullscreen=!!cameraFullscreenElement(),vv=window.visualViewport||null,w=0,h=0,l=0,t=0;if(vv&&!fullscreen){w=Math.max(1,Math.round(vv.width||0));h=Math.max(1,Math.round(vv.height||0));l=Math.max(0,Math.round(vv.offsetLeft||0));t=Math.max(0,Math.round(vv.offsetTop||0));}else{w=Math.max(1,Math.round(window.innerWidth||document.documentElement.clientWidth||1));h=Math.max(1,Math.round(window.innerHeight||document.documentElement.clientHeight||1));}liveCamera.style.setProperty('--sc-camera-vv-left',l+'px');liveCamera.style.setProperty('--sc-camera-vv-top',t+'px');liveCamera.style.setProperty('--sc-camera-vv-width',w+'px');liveCamera.style.setProperty('--sc-camera-vv-height',h+'px');});}
function resetLiveCameraViewport(){if(cameraViewportRaf){window.cancelAnimationFrame(cameraViewportRaf);cameraViewportRaf=0;}if(!liveCamera)return;liveCamera.style.removeProperty('--sc-camera-vv-left');liveCamera.style.removeProperty('--sc-camera-vv-top');liveCamera.style.removeProperty('--sc-camera-vv-width');liveCamera.style.removeProperty('--sc-camera-vv-height');}
function stopLiveCamera(){cameraRequestGeneration+=1;if(cameraZoomRaf){window.cancelAnimationFrame(cameraZoomRaf);cameraZoomRaf=0;}if(cameraHintTimer){window.clearTimeout(cameraHintTimer);cameraHintTimer=0;}if(cameraHint) cameraHint.hidden=true;cameraPinchStartDistance=0;cameraPinchStartZoom=1;cameraPendingZoom=1;cameraImageCapture=null;cameraCaptureBusy=false;if(cameraCapture){cameraCapture.disabled=false;cameraCapture.removeAttribute('aria-busy');cameraCapture.classList.remove('is-shooting');}if(cameraStream){cameraStream.getTracks().forEach(function(track){try{track.stop();}catch(error){}});cameraStream=null;}cameraTrack=null;cameraNativeZoom=false;cameraZoomValue=1;cameraZoomMin=1;cameraZoomMax=3;if(cameraVideo){try{cameraVideo.pause();}catch(error){}cameraVideo.srcObject=null;cameraVideo.style.transform='scale(1)';}exitCameraFullscreen();if(liveCamera) liveCamera.hidden=true;resetLiveCameraViewport();}
async function startRearCamera(){if(!state.isMobileCamera){chooseUpload();return;}scrollVisualizerTop();if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){intro.hidden=false;editor.hidden=true;if(deviceNote){deviceNote.textContent='Camera unavailable. You can choose a wall photo instead.';deviceNote.hidden=false;}if(cameraInput){cameraInput.value='';cameraInput.click();}return;}stopLiveCamera();var requestGeneration=cameraRequestGeneration,openedStream=null;if(!cameraArtworkPrimePromise)primeCameraArtwork();if(overlay) overlay.classList.remove('is-photo-ready');if(stickyBuy) stickyBuy.hidden=true;if(modal) modal.classList.remove('has-sticky-buy');if(liveCamera) liveCamera.hidden=false;syncLiveCameraViewport();requestCameraFullscreen();intro.hidden=true;editor.hidden=true;scrollVisualizerTop();var baseVideo={facingMode:{ideal:'environment'},width:{ideal:4096},height:{ideal:2160},frameRate:{ideal:24,max:30}};var exactVideo={facingMode:{exact:'environment'},width:{ideal:4096},height:{ideal:2160},frameRate:{ideal:24,max:30}};try{try{openedStream=await navigator.mediaDevices.getUserMedia({audio:false,video:exactVideo});}catch(firstError){if(requestGeneration!==cameraRequestGeneration||firstError.name==='NotAllowedError'||firstError.name==='SecurityError')throw firstError;openedStream=await navigator.mediaDevices.getUserMedia({audio:false,video:baseVideo});}if(requestGeneration!==cameraRequestGeneration||overlay.hidden){openedStream.getTracks().forEach(function(t){t.stop();});return;}cameraStream=openedStream;if(cameraVideo){cameraVideo.srcObject=cameraStream;await cameraVideo.play();syncLiveCameraViewport();if(cameraHint){cameraHint.hidden=false;if(cameraHintTimer) window.clearTimeout(cameraHintTimer);cameraHintTimer=window.setTimeout(function(){if(cameraHint) cameraHint.hidden=true;cameraHintTimer=0;},4200);}configureCameraZoom();await applyBestCameraImageSettings();try{if(cameraTrack&&typeof ImageCapture!=='undefined') cameraImageCapture=new ImageCapture(cameraTrack);}catch(imageCaptureError){cameraImageCapture=null;}scrollVisualizerTop();}}catch(error){if(requestGeneration!==cameraRequestGeneration)return;stopLiveCamera();if(deviceNote){deviceNote.textContent="Camera unavailable. You can choose a wall photo instead.";deviceNote.hidden=false;}if(state.photoReady){editor.hidden=false;setStagePhotoState();updateStickyBuy();}else{intro.hidden=false;}scrollVisualizerTop();if(cameraInput){cameraInput.value='';cameraInput.click();}}}
function captureRearCamera(){if(cameraCaptureBusy||!cameraVideo||!cameraVideo.videoWidth||!cameraVideo.videoHeight)return;if(cameraHintTimer){window.clearTimeout(cameraHintTimer);cameraHintTimer=0;}if(cameraHint)cameraHint.hidden=true;var captureSeq=++cameraCaptureSeq;cameraCaptureBusy=true;if(cameraCapture){cameraCapture.disabled=true;cameraCapture.setAttribute('aria-busy','true');cameraCapture.classList.add('is-shooting');}var frozen=freezeVisibleCameraFrame();if(!frozen){cameraCaptureBusy=false;if(cameraCapture){cameraCapture.disabled=false;cameraCapture.removeAttribute('aria-busy');cameraCapture.classList.remove('is-shooting');}return;}try{cameraVideo.pause();}catch(error){}showCaptureFreeze(frozen);renderCameraSourceToBlob(frozen,frozen.width,frozen.height,true).then(function(blob){if(captureSeq!==cameraCaptureSeq)return;stopLiveCamera();if(!blob)throw new Error('Camera image unavailable');activatePhoto(blob,true);}).catch(function(){if(captureSeq!==cameraCaptureSeq)return;stopLiveCamera();try{frozen.toBlob(function(blob){if(captureSeq!==cameraCaptureSeq)return;if(blob)activatePhoto(blob,true);else returnToPhotoStart();},'image/jpeg',.97);}catch(error){if(captureSeq===cameraCaptureSeq)returnToPhotoStart();}});}
function cancelRearCamera(){stopLiveCamera();if(state.photoReady){editor.hidden=false;intro.hidden=true;setStagePhotoState();updateStickyBuy();}else{editor.hidden=true;intro.hidden=false;}}
function chooseCamera(){if(!state.isMobileCamera){chooseUpload();return;}scrollVisualizerTop();startRearCamera();}
function chooseUpload(){scrollVisualizerTop();stopLiveCamera();if(!uploadInput) return;if(deviceNote) deviceNote.hidden=true;uploadInput.value='';uploadInput.click();}
function chooseUploadFromCamera(event){if(event){event.preventDefault();event.stopPropagation();}if(!uploadInput) return;if(cameraHintTimer){window.clearTimeout(cameraHintTimer);cameraHintTimer=0;}if(cameraHint) cameraHint.hidden=true;uploadInput.value='';uploadInput.click();}
function launchWallExperience(){
applyDeviceMode();
if(state.isMobileCamera){
showDialog(false);
primeCameraArtwork();
if(editor)editor.hidden=true;
startRearCamera();
return;
}
showDialog(true);
if(intro) intro.hidden=false;
if(editor) editor.hidden=true;
}

function mountOverlayToBody(){if(!overlay||overlay.parentNode===document.body) return;document.body.appendChild(overlay);if(liveCamera)overlay.appendChild(liveCamera);}
function restoreOverlayHome(){if(!overlay||!overlayHomeParent||overlay.parentNode===overlayHomeParent) return;if(overlayHomeNext&&overlayHomeNext.parentNode===overlayHomeParent) overlayHomeParent.insertBefore(overlay,overlayHomeNext);else overlayHomeParent.appendChild(overlay);}
function rememberPagePosition(){state.pageScrollX=window.scrollX||window.pageXOffset||0;state.pageScrollY=window.scrollY||window.pageYOffset||0;}
function restorePagePosition(){var x=state.pageScrollX,y=state.pageScrollY;window.requestAnimationFrame(function(){window.scrollTo(x,y);window.setTimeout(function(){window.scrollTo(x,y);},40);});}
function showDialog(showIntro){if(!overlay.hidden) return;lastActiveElement=document.activeElement;rememberPagePosition();syncFromProductPage();armOneTimeUpsizeCue();setUnit(currentUnitFromPicker(root)||state.unit);applyDeviceMode();setStagePhotoState();savedBodyOverflow=document.body.style.overflow||'';savedHtmlOverflow=document.documentElement.style.overflow||'';mountOverlayToBody();document.body.style.overflow='hidden';document.documentElement.style.overflow='hidden';overlay.style.setProperty('z-index','2147483600','important');overlay.hidden=false;overlay.setAttribute('aria-hidden','false');openButton.setAttribute('aria-expanded','true');modal.scrollTop=0;if(intro&&!state.photoReady) intro.hidden=showIntro===true?false:true;if(editor&&!state.photoReady) editor.hidden=true;warmCurrentArtwork();fireLocalPreviewEvent('WallPreviewStarted');updateStickyBuy();requestArtworkEffectsSync();restorePagePosition();if(introCloseButton)introCloseButton.focus({preventScroll:true});}
function closeDialog(){if(overlay.hidden) return;overlay.setAttribute('aria-hidden','true');overlay.hidden=true;overlay.style.removeProperty('z-index');openButton.setAttribute('aria-expanded','false');document.body.style.overflow=savedBodyOverflow;document.documentElement.style.overflow=savedHtmlOverflow;try{clearDesktopPreviewLayout();}catch(error){}try{closeSharePopup();}catch(error){}try{closeDownloadGate();}catch(error){}try{returnToPhotoStart();}catch(error){}if(cameraInput) cameraInput.value='';if(uploadInput) uploadInput.value='';try{stage.style.aspectRatio='';}catch(error){}if(stickyBuy) stickyBuy.hidden=true;try{modal.classList.remove('has-sticky-buy');}catch(error){}try{restoreOverlayHome();}catch(error){}try{restorePagePosition();}catch(error){}window.setTimeout(clearCartLayerIfClosed,0);if(lastActiveElement&&lastActiveElement.isConnected&&!document.body.classList.contains('sc-wall-cart-layer')){try{lastActiveElement.focus({preventScroll:true});}catch(error){try{lastActiveElement.focus();}catch(ignore){}}}lastActiveElement=null;}
function handleMainClose(event){if(event){event.preventDefault();event.stopPropagation();if(event.stopImmediatePropagation) event.stopImmediatePropagation();}closeDialog();return false;}

function beginDrag(event){if(state.confirmed||!state.photoReady||!previewIsReady()||state.calibrationActive||artCanvas.hidden)return;event.preventDefault();savedBlob=null;assetRevision+=1;assetPromise=null;savedFile=null;hidePlacementGuide();hideConfirmPrompt();state.dragging=true;state.dragPointerId=event.pointerId;state.dragStartX=event.clientX;state.dragStartY=event.clientY;state.dragStartCenterX=state.centerX;state.dragStartCenterY=state.centerY;artCanvas.classList.add('is-dragging');if(artCanvas.setPointerCapture){try{artCanvas.setPointerCapture(event.pointerId);}catch(error){}}}
function moveDrag(event){if(!state.dragging||event.pointerId!==state.dragPointerId) return;event.preventDefault();var rect=stage.getBoundingClientRect();if(!rect.width||!rect.height) return;var dx=event.clientX-state.dragStartX,dy=event.clientY-state.dragStartY;if(Math.sqrt(dx*dx+dy*dy)>=4) state.hasDraggedPlacement=true;state.centerX=clamp(state.dragStartCenterX+dx/rect.width*100,-100,200);state.centerY=clamp(state.dragStartCenterY+dy/rect.height*100,-100,200);applyArtworkPosition();}
function endDrag(event){if(!state.dragging) return;if(event&&state.dragPointerId!==null&&event.pointerId!==state.dragPointerId) return;state.dragging=false;artCanvas.classList.remove('is-dragging');if(event&&artCanvas.releasePointerCapture){try{artCanvas.releasePointerCapture(event.pointerId);}catch(error){}}state.dragPointerId=null;if(state.hasDraggedPlacement){showConfirmPrompt(40);window.setTimeout(primePreviewActionAsset,60);}else{showPlacementGuide();}}

async function buildCompositeCanvas(includeBrandOverlay,maxDimOverride,maxPixelsOverride){if(typeof includeBrandOverlay==='undefined') includeBrandOverlay=true;if(!state.photoReady||!previewIsReady()||artCanvas.hidden||!roomImage.naturalWidth||!roomImage.naturalHeight) throw new Error('Preview is not ready');var sourceW=roomImage.naturalWidth,sourceH=roomImage.naturalHeight,maxDim=Number(maxDimOverride)||6000,maxPixels=Number(maxPixelsOverride)||24000000;var scale=Math.min(1,maxDim/sourceW,maxDim/sourceH,Math.sqrt(maxPixels/(sourceW*sourceH)));var output=document.createElement('canvas');output.width=Math.max(1,Math.round(sourceW*scale));output.height=Math.max(1,Math.round(sourceH*scale));var ctx=output.getContext('2d');if(!ctx) throw new Error('Canvas is unavailable');ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(roomImage,0,0,output.width,output.height);ctx.save();ctx.fillStyle='rgba(241,232,217,.022)';ctx.fillRect(0,0,output.width,output.height);var ambient=ctx.createLinearGradient(0,0,0,output.height);ambient.addColorStop(0,'rgba(255,255,255,.012)');ambient.addColorStop(.58,'rgba(255,255,255,0)');ambient.addColorStop(1,'rgba(0,0,0,.036)');ctx.fillStyle=ambient;ctx.fillRect(0,0,output.width,output.height);ctx.restore();var artW=output.width*(state.artWidthPercent/100);var artH=artW*(artCanvas.height/artCanvas.width);var x=output.width*(state.centerX/100)-artW/2;var y=output.height*(state.centerY/100)-artH/2;var sampleBoxPadX=Math.max(12,artW*.08);var sampleBoxPadY=Math.max(12,artH*.08);function avgRegion(sx,sy,sw,sh){sx=Math.max(0,Math.round(sx));sy=Math.max(0,Math.round(sy));sw=Math.max(4,Math.round(sw));sh=Math.max(4,Math.round(sh));sw=Math.min(sw,output.width-sx);sh=Math.min(sh,output.height-sy);if(sw<1||sh<1) return {r:225,g:228,b:231,l:228};var sample=document.createElement('canvas');sample.width=24;sample.height=24;var sctx=sample.getContext('2d',{willReadFrequently:true});sctx.drawImage(output,sx,sy,sw,sh,0,0,24,24);var d=sctx.getImageData(0,0,24,24).data;var r=0,g=0,b=0,c=0;for(var i=0;i<d.length;i+=4){if(d[i+3]<10) continue;r+=d[i];g+=d[i+1];b+=d[i+2];c++;}if(!c) return {r:225,g:228,b:231,l:228};r/=c;g/=c;b/=c;return {r:r,g:g,b:b,l:(.2126*r+.7152*g+.0722*b)};}var topAvg=avgRegion(x+artW*.16,Math.max(0,y-sampleBoxPadY),artW*.68,sampleBoxPadY);var leftAvg=avgRegion(Math.max(0,x-sampleBoxPadX),y+artH*.18,sampleBoxPadX,artH*.64);var rightAvg=avgRegion(Math.min(output.width-4,x+artW),y+artH*.18,sampleBoxPadX,artH*.64);var ambientAvg=topAvg||leftAvg||rightAvg;var bright=clamp((ambientAvg.l-124)/255,-.18,.18);var warm=clamp((ambientAvg.r-ambientAvg.b)/255,-.16,.16);var shadowBlur=Math.max(10,artW*.07);var contactBlur=Math.max(4,artW*.024);ctx.save();ctx.shadowColor='rgba(0,0,0,'+(0.16+Math.max(0,.08-bright*.2)).toFixed(3)+')';ctx.shadowBlur=shadowBlur;ctx.shadowOffsetY=Math.max(4,artW*.024);ctx.shadowOffsetX=Math.max(1,artW*.005);ctx.fillStyle='rgba(0,0,0,.001)';ctx.fillRect(x,y,artW,artH);ctx.restore();ctx.save();ctx.shadowColor='rgba(0,0,0,.10)';ctx.shadowBlur=contactBlur;ctx.shadowOffsetY=Math.max(2,artW*.008);ctx.fillStyle='rgba(0,0,0,.001)';ctx.fillRect(x,y,artW,artH);ctx.restore();ctx.save();ctx.filter='brightness('+(0.988+bright*.16).toFixed(3)+') contrast('+(0.992+bright*.04).toFixed(3)+') saturate('+(0.992+warm*.08).toFixed(3)+')';var shear=clamp((state.centerX-50)/50,-1,1)*0.015;ctx.setTransform(1,shear,-shear*.22,1,0,0);ctx.drawImage(artCanvas,x,y-(shear*artW*.04),artW,artH);ctx.setTransform(1,0,0,1,0,0);ctx.restore();ctx.save();var frameWash=ctx.createLinearGradient(x,y,x+artW,y+artH);frameWash.addColorStop(0,'rgba('+Math.round(ambientAvg.r)+','+Math.round(ambientAvg.g)+','+Math.round(ambientAvg.b)+','+(0.022+Math.abs(warm)*.035).toFixed(3)+')');frameWash.addColorStop(.56,'rgba(255,255,255,0)');frameWash.addColorStop(1,'rgba(12,14,18,.022)');ctx.fillStyle=frameWash;ctx.fillRect(x,y,artW,artH);var glaze=ctx.createLinearGradient(x,y,x+artW,y+artH);glaze.addColorStop(0,'rgba(255,255,255,'+(0.065+Math.max(0,bright*.12)).toFixed(3)+')');glaze.addColorStop(.12,'rgba(255,255,255,'+(0.026+Math.max(0,bright*.05)).toFixed(3)+')');glaze.addColorStop(.3,'rgba(255,255,255,0)');glaze.addColorStop(.58,'rgba(255,255,255,.020)');glaze.addColorStop(.77,'rgba(255,255,255,0)');ctx.fillStyle=glaze;ctx.fillRect(x,y,artW,artH);ctx.strokeStyle='rgba(255,255,255,.038)';ctx.lineWidth=Math.max(1,output.width*.001);ctx.strokeRect(x+.5,y+.5,artW-1,artH-1);ctx.beginPath();ctx.strokeStyle='rgba(0,0,0,.09)';ctx.lineWidth=Math.max(1,output.width*.0012);ctx.moveTo(x+artW-.5,y+Math.max(2,artH*.03));ctx.lineTo(x+artW-.5,y+artH-.5);ctx.lineTo(x+Math.max(2,artW*.03),y+artH-.5);ctx.stroke();ctx.restore();try{var grain=document.createElement('canvas');grain.width=Math.max(16,Math.round(artW*.12));grain.height=Math.max(16,Math.round(artH*.12));var gctx=grain.getContext('2d',{willReadFrequently:true});var id=gctx.createImageData(grain.width,grain.height);for(var p=0;p<id.data.length;p+=4){var n=128+Math.round((Math.random()-.5)*18);id.data[p]=n;id.data[p+1]=n;id.data[p+2]=n;id.data[p+3]=10;}gctx.putImageData(id,0,0);ctx.save();ctx.globalAlpha=.08;ctx.globalCompositeOperation='soft-light';ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='medium';ctx.drawImage(grain,x,y,artW,artH);ctx.restore();}catch(error){}if(includeBrandOverlay){if(logoUrl){try{var logo=await loadImage(logoUrl);var maxLogoW=artW*.72;var maxLogoH=artH*.34;var logoScale=Math.min(maxLogoW/logo.naturalWidth,maxLogoH/logo.naturalHeight);var logoW=logo.naturalWidth*logoScale;var logoH=logo.naturalHeight*logoScale;ctx.save();ctx.globalAlpha=.17;ctx.drawImage(logo,x+(artW-logoW)/2,y+(artH-logoH)/2,logoW,logoH);ctx.restore();}catch(error){}}var credit='@sportscaveshop  •  sportscaveshop.com';var creditFont=Math.max(18,Math.min(34,output.width*.018));ctx.save();ctx.font='700 '+creditFont+'px Montserrat, Arial, sans-serif';ctx.textBaseline='middle';var creditWidth=ctx.measureText(credit).width;var padX=creditFont*.8;var padY=creditFont*.52;var creditBoxW=Math.min(output.width*.88,creditWidth+padX*2);var creditBoxH=creditFont+padY*2;var creditX=(output.width-creditBoxW)/2;var creditY=output.height-creditBoxH-Math.max(18,output.height*.035);var radius=Math.min(creditBoxH/2,creditFont*.7);ctx.beginPath();ctx.moveTo(creditX+radius,creditY);ctx.lineTo(creditX+creditBoxW-radius,creditY);ctx.quadraticCurveTo(creditX+creditBoxW,creditY,creditX+creditBoxW,creditY+radius);ctx.lineTo(creditX+creditBoxW,creditY+creditBoxH-radius);ctx.quadraticCurveTo(creditX+creditBoxW,creditY+creditBoxH,creditX+creditBoxW-radius,creditY+creditBoxH);ctx.lineTo(creditX+radius,creditY+creditBoxH);ctx.quadraticCurveTo(creditX,creditY+creditBoxH,creditX,creditY+creditBoxH-radius);ctx.lineTo(creditX,creditY+radius);ctx.quadraticCurveTo(creditX,creditY,creditX+radius,creditY);ctx.closePath();ctx.fillStyle='rgba(11,11,13,.56)';ctx.fill();ctx.strokeStyle='rgba(212,165,76,.38)';ctx.lineWidth=Math.max(1,output.width*.0009);ctx.stroke();ctx.fillStyle='rgba(255,252,247,.94)';ctx.textAlign='center';ctx.shadowColor='rgba(0,0,0,.30)';ctx.shadowBlur=Math.max(1,output.width*.0015);ctx.fillText(credit,output.width/2,creditY+creditBoxH/2+.5);ctx.restore();}return output;}
function canvasToBlob(canvas,type,quality){return new Promise(function(resolve,reject){canvas.toBlob(function(blob){if(blob) resolve(blob);else reject(new Error('Could not create preview image'));},type||'image/jpeg',quality||.94);});}
function previewFilename(){var handle=root.getAttribute('data-product-handle')||'sports-cave';return 'sports-cave-'+handle+'-wall-preview.jpg';}
function downloadBlob(blob){var url=URL.createObjectURL(blob);var link=document.createElement('a');link.href=url;link.download=previewFilename();document.body.appendChild(link);link.click();link.remove();window.setTimeout(function(){URL.revokeObjectURL(url);},1800);}
function canNativeShareFile(file){try{return !!(navigator.share&&navigator.canShare&&navigator.canShare({files:[file]}));}catch(error){return false;}}
async function ensureSavedPreviewAsset(retainComposite){
if(savedBlob) return retainComposite?savedBlob:true;
var revision=assetRevision;
if(!assetPromise){
assetPromise=(async function(){try{
var canvas=await buildCompositeCanvas(true,3200,8000000);
var blob=await canvasToBlob(canvas,'image/jpeg',.92);
if(!blob) return null;
if(revision===assetRevision){
savedBlob=blob;
try{savedFile=new File([blob],previewFilename(),{type:'image/jpeg'});}catch(error){savedFile=null;}
setPreviewActionState();}
return blob;
}catch(error){return null;}}());
}
var pending=assetPromise;
try{var blob=await pending;return retainComposite?blob:!!(blob&&revision===assetRevision);}finally{if(assetPromise===pending) assetPromise=null;}
}
function archiveMetadata(identityOverride,featurePermission){
var variant=currentVariant(),identity=identityOverride||loggedInIdentity();
if(!identity||!validIdentityEmail(identity.email)) identity=sessionDownloadIdentity();
var params=new URLSearchParams();
params.set('client_preview_id',state.clientPreviewId);params.set('session_id',sessionId);
params.set('finished_composite','1');
params.set('product_id',String(root.getAttribute('data-product-id')||''));
params.set('variant_id',variant&&variant.id?String(variant.id):'');
params.set('product_handle',String(root.getAttribute('data-product-handle')||''));
params.set('product_title',String(root.getAttribute('data-product-title')||''));
params.set('product_url',shareProductUrl());params.set('frame',frameName(state.frame));
params.set('size',state.sizeInfo?(state.sizeInfo.token+' • '+formatSize(state.sizeInfo,state.unit)):'');
params.set('unit',state.unit||'');
if(root.getAttribute('data-market-country-code')) params.set('market_country_code',root.getAttribute('data-market-country-code'));if(root.getAttribute('data-market-country-name')) params.set('market_country_name',root.getAttribute('data-market-country-name'));
if(typeof featurePermission==='boolean'){params.set('image_reuse_allowed',featurePermission?'1':'0');params.set('reuse_consent_source','wall_preview_download_checkbox');}
params.set('customer_email',identity&&identity.email||'');params.set('customer_name',identity&&identity.name||'');
params.set('identity_source',identity&&identity.source||'anonymous');
return params;
}

async function archivePreview(blob,timeoutMs,identityOverride,featurePermission,metadata){

var endpoint=String(root.getAttribute('data-wall-inbox-url')||'').trim();
if(!endpoint||!blob) return {ok:false,skipped:true};

var params=metadata||archiveMetadata(identityOverride,featurePermission);
var controller=typeof AbortController!=='undefined'?new AbortController():null;
var timeoutId=controller?window.setTimeout(function(){controller.abort();},Math.max(5000,Number(timeoutMs)||15000)):0;
try{
var response=await fetch(endpoint+'?'+params.toString(),{
method:'POST',
headers:{'Accept':'application/json','Content-Type':'image/jpeg'},
body:blob,
mode:'cors',
credentials:'omit',
signal:controller?controller.signal:undefined
});
if(!response.ok){var failure=new Error('Preview archive failed ('+response.status+')');
if(response.status===429||response.status===503){var retrySeconds=Number(response.headers.get('Retry-After'));if(Number.isFinite(retrySeconds)&&retrySeconds>0) failure.retryAfterMs=Math.min(retrySeconds,900)*1000+1000;}
throw failure;}

var data=await response.json();
if(!data||data.ok!==true||!data.preview_id) throw new Error('Preview was not persisted');
if(params.get('client_preview_id')!==state.clientPreviewId) return data;
state.storageAccepted=true;state.archiveStatus=String(data.archive_status||'accepted');state.storageSaved=state.archiveStatus==='archived';

if(data){
var nested=data.preview&&typeof data.preview==='object'?data.preview:null;
state.previewId=String(data.preview_id||data.id||(nested&&(nested.preview_id||nested.id))||state.previewId||'');
state.shareUrl=String(data.share_url||(nested&&nested.share_url)||state.shareUrl||'');
}
return data||{ok:true};
}finally{
if(timeoutId) window.clearTimeout(timeoutId);
}
}
async function archiveWithRetry(blob,identity,featurePermission,metadata){var delays=[0,600,1800];var lastError=null;for(var i=0;i<delays.length;i+=1){var delay=Math.max(delays[i],lastError&&lastError.retryAfterMs||0);if(delay) await new Promise(function(resolve){window.setTimeout(resolve,delay);});try{return await archivePreview(blob,15000,identity,featurePermission,metadata);}catch(error){lastError=error;}}throw lastError||new Error('Preview archive failed');}
function fireLocalPreviewEvent(name,detail){var variant=currentVariant();var payload=Object.assign({event:name,preview_id:state.previewId||'',client_preview_id:state.clientPreviewId||'',product_id:String(root.getAttribute('data-product-id')||''),product_handle:String(root.getAttribute('data-product-handle')||''),frame:frameName(state.frame),size:state.sizeInfo?state.sizeInfo.token:'',variant_id:variant&&variant.id?String(variant.id):''},detail||{});try{document.dispatchEvent(new CustomEvent('sports-cave:wall-preview',{detail:payload}));}catch(error){}try{window.dataLayer=window.dataLayer||[];window.dataLayer.push(Object.assign({event:name},payload));}catch(error){}}
function emitPreviewEvent(name,extra){fireLocalPreviewEvent(name,extra);var aliases={WallPreviewDownloaded:'wall_preview_downloaded',WallPreviewShared:'wall_preview_shared',WallPreviewAddedToCart:'wall_preview_add_to_cart'};if(aliases[name]) fireLocalPreviewEvent(aliases[name],extra);if(!state.previewId||['WallPreviewDownloaded','WallPreviewShared','WallPreviewAddedToCart'].indexOf(name)<0) return;var endpoint=String(root.getAttribute('data-wall-inbox-url')||'').trim();if(!endpoint) return;try{fetch(endpoint+'/'+encodeURIComponent(state.previewId)+'/events',{method:'POST',headers:{'Accept':'application/json','Content-Type':'application/json','X-Wall-Preview-Token':sessionId},body:JSON.stringify({event_name:name,event_id:makeId(),occurred_at:new Date().toISOString()}),mode:'cors',credentials:'omit',keepalive:true}).catch(function(){});}catch(error){}}
function queuePreviewSave(blob,identity,permission,metadata){
var snapshot=new URLSearchParams(metadata||archiveMetadata(identity,permission));
// One existing preview UUID per deliberate capture, reused only by its network retries.
// Each capture owns its durable row/job, so rapid saves cannot replace queued images.
state.clientPreviewId=makeId('preview');snapshot.set('client_preview_id',state.clientPreviewId);
snapshot.set('capture_mode','save_event');
state.previewId='';state.shareUrl='';state.storageSaved=false;state.storageAccepted=false;state.archiveStatus='';
// Serialize uploads; a failed capture never prevents the next capture from running.
var job=saveTail.catch(function(){}).then(async function(){var image=await blob;if(!image) throw new Error('Preview image unavailable');return archiveWithRetry(image,identity,permission,snapshot);});
saveTail=job;archivePromise=job;
job.then(function(result){fireLocalPreviewEvent(result.archive_status==='archived'?'wall_preview_saved':'wall_preview_save_queued',{client_preview_id:snapshot.get('client_preview_id'),archive_status:result.archive_status||'accepted'});},function(){try{console.warn('[Sports Cave Wall Preview] save pending; retry on next Place or Download');}catch(error){}});
return job;
}
function startPlacementPersistenceInBackground(){
if(!state.confirmed||!state.photoReady) return;
var metadata=archiveMetadata();
fireLocalPreviewEvent('wall_preview_placed');
queuePreviewSave(ensureSavedPreviewAsset(true),null,undefined,metadata).catch(function(){});
}

function handleConfirmPlacement(){
if(state.confirming||state.confirmed||!state.photoReady||!previewIsReady()||artCanvas.hidden) return;
state.confirming=true;
hidePlacementGuide();
if(confirmButton) confirmButton.classList.add('is-loading');
if(confirmPromptEl) confirmPromptEl.hidden=false;
if(confirmLabel) confirmLabel.textContent='Placing';
setShareNote('');


window.setTimeout(function(){
if(!state.confirming) return;
state.confirming=false;
if(confirmButton) confirmButton.classList.remove('is-loading');
markConfirmedUi();
updateStickyBuy();
requestArtworkEffectsSync();

startPlacementPersistenceInBackground();
},90);
}
async function ensureArchiveSynced(){if(state.storageSaved) return true;if(archivePromise){try{await archivePromise;}catch(error){}}if(state.storageSaved) return true;if(lastArchiveBlob){try{archivePromise=archiveWithRetry(lastArchiveBlob);await archivePromise;return !!state.storageSaved;}catch(error){}}return false;}

function primePreviewActionAsset(){if(!savedBlob&&state.photoReady&&previewIsReady()&&!artCanvas.hidden) ensureSavedPreviewAsset();}

function ensurePreviewActionPlacement(){if(state.confirmed) return true;if(!state.photoReady||!previewIsReady()||artCanvas.hidden) return false;state.confirming=false;state.hasDraggedPlacement=true;markConfirmedUi();startPlacementPersistenceInBackground();return true;}
function requestDownloadPreview(event){if(event){event.preventDefault();event.stopPropagation();}if(!saveButton||!ensurePreviewActionPlacement()) return;openDownloadGate();}
async function downloadConfirmedPreview(){
if(!state.confirmed||!downloadConfirm||downloadConfirm.disabled) return;
var identity=downloadIdentityFromGate();
if(!identity) return;
var allowFeature=!!(downloadConsent&&downloadConsent.checked);
rememberDownloadIdentity(identity);
downloadConfirm.disabled=true;
downloadConfirm.textContent='Preparing…';
setDownloadError('');
setShareNote('');
try{
var ready=await ensureSavedPreviewAsset();
if(!ready||!savedBlob) throw new Error('Preview image unavailable');

downloadBlob(savedBlob);
emitPreviewEvent('WallPreviewDownloaded');
closeDownloadGate();
if(saveLabel) saveLabel.textContent='Downloaded ✓';if(saveButton){saveButton.setAttribute('aria-label','Downloaded');saveButton.setAttribute('title','Downloaded');}
setShareNote('Downloaded — saving your Sports Cave copy…');

archivePromise=queuePreviewSave(savedBlob,identity,allowFeature);
var downloadCapture=state.clientPreviewId;
// Release the local Download action immediately; storage must not gate the next save.
archivePromise.then(function(archive){
if(state.clientPreviewId!==downloadCapture) return;
setShareNote(archive&&archive.archive_status==='archived'?'Downloaded — Sports Cave copy saved.':'Downloaded to your device.');
},function(){if(state.clientPreviewId===downloadCapture) setShareNote('Downloaded to your device.');});
}catch(error){
if(savedBlob){
setShareNote('Downloaded to your device.');
try{console.warn('[Sports Cave Wall Preview] customer archive pending',error);}catch(logError){}
}else{
setDownloadError('Could not prepare this preview. Please try again.');
if(downloadGate){downloadGate.hidden=false;downloadGate.setAttribute('aria-hidden','false');}
}
}finally{
if(downloadConfirm){downloadConfirm.disabled=false;downloadConfirm.textContent='Download Preview';}
window.setTimeout(function(){if(saveLabel&&state.confirmed) saveLabel.textContent='Download Your Preview';if(saveButton&&state.confirmed){saveButton.setAttribute('aria-label','Download your wall preview');saveButton.setAttribute('title','Download preview');}},1600);
}
}
function shareProductUrl(){try{var url=new URL(window.location.href);url.hash='';var variant=currentVariant();if(variant&&variant.id){url.searchParams.set('variant',String(variant.id));}return url.href;}catch(error){return window.location.href;}}
function setSharePreviewLabel(text){var label=text||'Share Preview';if(sharePreviewLabel) sharePreviewLabel.textContent=label;if(sharePreviewButton){sharePreviewButton.setAttribute('aria-label',label);sharePreviewButton.setAttribute('title',label);}}
function copyShareText(text){try{if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(text).catch(function(){});return true;}}catch(error){}try{var area=document.createElement('textarea');area.value=text;area.setAttribute('readonly','');area.style.position='fixed';area.style.left='-9999px';document.body.appendChild(area);area.select();var ok=document.execCommand('copy');area.remove();return !!ok;}catch(error){return false;}}
function shareConfirmedPreview(event){
if(event){event.preventDefault();event.stopPropagation();}
if(!sharePreviewButton||!ensurePreviewActionPlacement()) return;
var productUrl=state.shareUrl||shareProductUrl();
var productTitle=String(root.getAttribute('data-product-title')||'Sports Cave Edition').trim();
var shareText='See '+productTitle+' on my wall. @sportscaveshop\n'+productUrl;
if(!savedFile&&savedBlob){try{savedFile=new File([savedBlob],previewFilename(),{type:'image/jpeg'});}catch(fileError){savedFile=null;}}
try{
sharePreviewButton.disabled=true;
setSharePreviewLabel('Opening Share…');
var sharePromise=null;
if(savedFile&&canNativeShareFile(savedFile)){
sharePromise=navigator.share({files:[savedFile],title:productTitle+' | Sports Cave',text:shareText});
}else if(navigator.share){
sharePromise=navigator.share({title:productTitle+' | Sports Cave',text:shareText,url:productUrl});
}else{
copyShareText(shareText);
setSharePreviewLabel('Link Copied ✓');
sharePreviewButton.disabled=false;
primePreviewActionAsset();
return;
}
Promise.resolve(sharePromise).then(function(){
emitPreviewEvent('WallPreviewShared');
setSharePreviewLabel('Shared ✓');
}).catch(function(error){
if(error&&error.name==='AbortError'){setSharePreviewLabel('Share Preview');}
else{copyShareText(shareText);setSharePreviewLabel('Link Copied ✓');}
}).finally(function(){
window.setTimeout(function(){
if(state.photoReady&&previewIsReady()&&!artCanvas.hidden){sharePreviewButton.disabled=false;setSharePreviewLabel('Share Preview');}
},900);
});
primePreviewActionAsset();
}catch(error){
copyShareText(shareText);
setSharePreviewLabel('Link Copied ✓');
sharePreviewButton.disabled=false;
primePreviewActionAsset();
}
}
function closeSharePopup(){}
function cssEscape(value){value=String(value||'');if(window.CSS&&typeof window.CSS.escape==='function') return window.CSS.escape(value);return value.replace(/"/g,'\\"');}
function optionGroup(optionName){var picker=productPickerFor(root);if(!picker) return null;optionName=String(optionName||'').toLowerCase();var groups=picker.querySelectorAll('.option-selector');for(var i=0;i<groups.length;i++){var name=String(groups[i].getAttribute('data-option')||'').toLowerCase();if(name===optionName) return groups[i];}return null;}
function optionValue(group){if(!group) return null;var picker=productPickerFor(root);var checked=group.querySelector('input.js-option:checked')||group.querySelector('input[type="radio"]:checked')||group.querySelector('input.js-option:not([disabled])');if(!checked) return null;var label=checked.id&&picker?picker.querySelector('label[for="'+cssEscape(checked.id)+'"]'):null;var valueNode=label?label.querySelector('.js-value'):null;return String((valueNode?valueNode.textContent:checked.value)||'').trim();}
function selectedOptions(){return PRODUCT_OPTS.map(function(optionName){var name=String(optionName||'').toLowerCase();if(name.indexOf('size')>-1&&state.sizeRaw) return state.sizeRaw;return optionValue(optionGroup(optionName));});}
function variantFromPageForm(){var picker=productPickerFor(root);var scope=picker&&picker.closest?picker.closest('product-info,.product,.product-info,[data-product-id],[id^="shopify-section-"],.shopify-section'):null;var inputs=(scope||document).querySelectorAll('form[action*="/cart/add"] input[name="id"],input[name="id"][data-variant-id]');for(var i=0;i<inputs.length;i+=1){var id=Number(inputs[i].value||inputs[i].getAttribute('data-variant-id')||0);if(!id) continue;var match=VARIANTS.find(function(v){return v&&Number(v.id)===id;});if(match) return match;}return null;}
function currentVariant(){var chosen=selectedOptions();var exact=VARIANTS.find(function(variant){if(!variant||!variant.options) return false;for(var i=0;i<chosen.length;i++){if(chosen[i]&&String(variant.options[i])!==String(chosen[i])) return false;}return true;});if(exact) return exact;var fromForm=variantFromPageForm();if(fromForm) return fromForm;try{var variantParam=Number(new URL(window.location.href).searchParams.get('variant')||0);if(variantParam){var fromUrl=VARIANTS.find(function(v){return v&&Number(v.id)===variantParam;});if(fromUrl) return fromUrl;}}catch(error){}return VARIANTS[0]||null;}
function routeRoot(){var rootPath='/';try{if(window.Shopify&&window.Shopify.routes&&window.Shopify.routes.root) rootPath=window.Shopify.routes.root;}catch(error){}rootPath=String(rootPath||'/');if(rootPath.slice(-1)!=='/') rootPath+='/';return rootPath;}
function route(path){return routeRoot()+String(path||'').replace(/^\//,'');}
function cartDrawer(){return document.querySelector('cart-drawer.js-cart-drawer, cart-drawer, #CartDrawer, #Cart-Drawer, .drawer.js-cart-drawer, .cart-drawer');}
function drawerIsOpen(drawer){if(!drawer) return false;return drawer.getAttribute('aria-hidden')==='false'||drawer.hasAttribute('open')||drawer.classList.contains('is-open')||drawer.classList.contains('active')||drawer.classList.contains('open');}
function clearCartLayerIfClosed(){var drawer=cartDrawer();if(drawerIsOpen(drawer)) return;document.body.classList.remove('sc-wall-cart-layer');if(overlay&&!overlay.hidden) overlay.style.setProperty('z-index','2147483600','important');}
function sectionIds(){var ids=[],seen={};function add(id){id=String(id||'').trim();if(id&&!seen[id]){seen[id]=true;ids.push(id);}}var drawer=cartDrawer();if(drawer){var section=drawer.closest('section[id^="shopify-section-"], .shopify-section[id^="shopify-section-"]');if(section) add(section.id.replace('shopify-section-',''));add(drawer.getAttribute('data-section-id'));drawer.querySelectorAll('[data-section-id]').forEach(function(node){add(node.getAttribute('data-section-id'));});}add('cart-drawer');return ids;}
function innerHTML(html,id){var temp=document.createElement('div');temp.innerHTML=html;var wrap=temp.querySelector('#shopify-section-'+id);return wrap?wrap.innerHTML:html;}
function applySections(sections){if(!sections) return false;var done=false;Object.keys(sections).forEach(function(id){var html=sections[id];if(typeof html!=='string'||!html) return;var host=document.getElementById('shopify-section-'+id);if(host){host.innerHTML=innerHTML(html,id);done=true;return;}if(id==='cart-drawer'){var drawer=cartDrawer();var temp=document.createElement('div');temp.innerHTML=html;var incoming=temp.querySelector('cart-drawer, #CartDrawer, #Cart-Drawer, .drawer.js-cart-drawer, .cart-drawer');if(drawer&&incoming){drawer.replaceWith(incoming);done=true;}}});return done;}
async function fetchCart(){var response=await fetch(route('cart.js'),{headers:{'Accept':'application/json'},credentials:'same-origin'});return response.json();}
function updateCartBubble(count){count=Number(count||0);var selector='#cart-icon-bubble, .cart-count-bubble, [data-cart-count-bubble], #CartCount, .site-header__cart-count, .cart__badge, .header__icon--cart .cart-count';document.querySelectorAll(selector).forEach(function(el){if(el.closest('cart-drawer, #CartDrawer, #Cart-Drawer, .cart-drawer, .drawer.js-cart-drawer')) return;var holder=el.querySelector('[aria-hidden="true"]')||el.querySelector('.cart-count, .cart-count-bubble__text')||el.firstElementChild||el;holder.textContent=String(count);el.setAttribute('data-cart-count',String(count));el.classList.toggle('is-empty',count===0);el.classList.toggle('hidden',count===0);if('hidden' in el) el.hidden=count===0;});}
function markDrawerFilled(count){var drawer=cartDrawer();if(!drawer) return;var show=Number(count||0)>0;['.cart-drawer__content','.cart-drawer__footer'].forEach(function(selector){var el=drawer.querySelector(selector);if(!el) return;el.hidden=!show;el.style.display=show?'':'none';});var empty=drawer.querySelector('.cart-drawer__empty-content');if(empty){empty.hidden=show;empty.style.display=show?'none':'';}drawer.querySelectorAll('.checkout-buttons, .verna-pay, .sc-cart-guarantee').forEach(function(el){el.hidden=!show;el.style.display=show?'':'none';});drawer.setAttribute('data-sc-cart-count',String(count||0));}
function dispatchCartEvents(cart){['cart:updated','cart:refresh','dispatch:cart-drawer:refresh','ajaxProduct:added'].forEach(function(name){try{document.dispatchEvent(new CustomEvent(name,{bubbles:true,detail:{cart:cart,source:'sports-cave-wall-visualizer'}}));}catch(error){}});}
function elevateCartDrawer(){var drawer=cartDrawer();if(!drawer) return false;document.body.classList.add('sc-wall-cart-layer');if(overlay) overlay.style.setProperty('z-index','2147483600','important');var section=drawer.closest('[id^="shopify-section-"],.shopify-section');if(section){section.style.setProperty('position','relative','important');section.style.setProperty('z-index','2147483646','important');}drawer.style.setProperty('z-index','2147483647','important');var backdrop=document.querySelector('[data-sc-cart-backdrop],.sc-cart-backdrop,[data-drawer-overlay]');if(backdrop){backdrop.style.setProperty('z-index','2147483645','important');if(drawer.getAttribute('aria-hidden')==='false'||drawer.classList.contains('is-open')){backdrop.classList.remove('hidden');backdrop.setAttribute('aria-hidden','false');}}return true;}function verifyCartDrawerLayer(){if(!overlay||overlay.hidden) return;var drawer=cartDrawer();if(!drawer) return;var rect=drawer.getBoundingClientRect();if(rect.width<20||rect.height<20) return;var x=Math.max(2,Math.min(window.innerWidth-2,rect.left+Math.min(rect.width*.5,Math.max(12,rect.width-12))));var y=Math.max(2,Math.min(window.innerHeight-2,rect.top+Math.min(72,Math.max(12,rect.height-12))));var topEl=document.elementFromPoint(x,y);if(topEl&&(topEl===drawer||drawer.contains(topEl))) return;closeDialog();}function openCartDrawer(){elevateCartDrawer();try{document.dispatchEvent(new CustomEvent('dispatch:cart-drawer:open',{bubbles:true,detail:{source:'sports-cave-wall-visualizer'}}));document.dispatchEvent(new CustomEvent('cart:open',{bubbles:true,detail:{source:'sports-cave-wall-visualizer'}}));}catch(error){}var drawer=cartDrawer();if(!drawer){closeDialog();return;}elevateCartDrawer();try{if(typeof drawer.open==='function') drawer.open();drawer.setAttribute('open','');drawer.setAttribute('aria-hidden','false');drawer.removeAttribute('inert');drawer.classList.add('is-open','active','open');document.body.classList.add('drawer-open','cart-drawer-open');}catch(error){}window.setTimeout(function(){elevateCartDrawer();verifyCartDrawerLayer();},450);}
async function renderCart(ids,addJson){if(addJson&&addJson.sections){applySections(addJson.sections);}else if(ids.length){try{var response=await fetch(route('?sections='+encodeURIComponent(ids.join(','))),{headers:{'Accept':'application/json'},credentials:'same-origin'});if(response.ok) applySections(await response.json());}catch(error){}}var cart=null;try{cart=await fetchCart();}catch(error){}var count=cart&&typeof cart.item_count==='number'?cart.item_count:1;updateCartBubble(count);markDrawerFilled(count);dispatchCartEvents(cart);return cart;}
function editionArchived(){return root.getAttribute('data-edition-expired')==='1';}
function setCartLoading(loading){
if(!stickySecure) return;
stickySecure.classList.toggle('is-loading',!!loading);
if(loading){
stickySecure.disabled=true;
stickySecure.setAttribute('aria-busy','true');
return;
}
stickySecure.removeAttribute('aria-busy');
setStickyCartState();
}
function setStickyCartState(){
if(!stickySecure) return;
var archived=editionArchived();
var variant=currentVariant();
stickySecure.classList.toggle('is-edition-archived',archived);

stickySecure.disabled=archived;
stickySecure.setAttribute('aria-disabled',archived?'true':'false');
if(stickyCartLabel) stickyCartLabel.textContent=archived?'Edition Archived':'Add To Cart';
if(stickyCartPrice){
var fmt=variant&&variant.id?(FORMATTED[String(variant.id)]||FORMATTED[variant.id]||{}):{};
stickyCartPrice.textContent=!archived&&fmt.price?((fmt.pricePrefix||'')+fmt.price):'';
}
}
function selectedVariantForCart(){
var variant=currentVariant();
if(variant&&variant.id) return variant;
var picker=productPickerFor(root);
var secure=picker?picker.querySelector('.sc-secure-edition'):null;
var idInput=secure?secure.querySelector('input[name="id"], [data-sc-secure-edition-variant-input]'):null;
var id=Number(idInput&&idInput.value||0);
if(id){
var matched=VARIANTS.find(function(item){return item&&Number(item.id)===id;});
if(matched) return matched;
return {id:id};
}
return VARIANTS[0]||null;
}
async function addSelectedVariantToCart(){
if(!stickySecure||editionArchived()) return;
var variant=selectedVariantForCart();
if(!variant||!variant.id){
if(stickyCartError){stickyCartError.textContent='Could not identify this edition. Please try again.';stickyCartError.classList.add('is-visible');}
return;
}
setCartLoading(true);
if(stickyCartError){stickyCartError.textContent='';stickyCartError.classList.remove('is-visible');}
var ids=sectionIds();
var picker=productPickerFor(root);
var secure=picker?picker.querySelector('.sc-secure-edition'):null;
var pageForm=secure?secure.querySelector('form'):null;
var fd=pageForm?new FormData(pageForm):new FormData();
fd.set('id',String(variant.id));
fd.set('quantity','1');
if(state.previewId) fd.set('properties[_wall_preview_id]',String(state.previewId));
if(state.clientPreviewId) fd.set('properties[_wall_preview_client_id]',String(state.clientPreviewId));
if(ids.length){fd.set('sections',ids.join(','));fd.set('sections_url',window.location.pathname);}
try{
var response=await fetch(route('cart/add.js'),{method:'POST',headers:{'Accept':'application/json'},body:fd,credentials:'same-origin'});
var json=null;
try{json=await response.json();}catch(error){}
if(!response.ok) throw new Error(json&&(json.description||json.message)?(json.description||json.message):'Cart add failed');
if(stickyCartLabel) stickyCartLabel.textContent='Added';
if(state.previewId) emitPreviewEvent('WallPreviewAddedToCart');
await renderCart(ids,json);
window.setTimeout(openCartDrawer,60);
}catch(error){
if(stickyCartError){stickyCartError.textContent=(error&&error.message)?error.message:'Could not add this edition. Please try again.';stickyCartError.classList.add('is-visible');}
}finally{
setCartLoading(false);
}
}
function updateStickyBuy(){if(!stickyBuy||!modal) return;var scalePending=!!(state.calibrationActive||state.awaitingMeasurement);var show=!!(state.photoReady&&!scalePending&&!overlay.hidden);stickyBuy.hidden=!show;modal.classList.toggle('has-sticky-buy',show);window.requestAnimationFrame(function(){if(show&&state.confirmed&&keepBrowsing&&keepBrowsing.getClientRects().length) modal.style.setProperty('padding-bottom',(stickyBuy.getBoundingClientRect().height+12)+'px','important');else modal.style.removeProperty('padding-bottom');syncDesktopPreviewLayout();});}

renderSizeButtons();setUnit(currentUnitFromPicker(root)||state.unit);syncFromProductPage();applyArtworkPosition();applyDeviceMode();setPreviewActionState();updateStatus();setStickyCartState();

listen(openButton,'click',function(event){event.preventDefault();launchWallExperience();});
var lastMainCloseAt=0;
function handleDelegatedMainClose(event){
var target=event.target&&event.target.closest?event.target.closest('[data-sc-wall-close],[data-sc-wall-intro-close]'):null;
if(!target||!overlay.contains(target)) return;
if(event.type==='click'&&Date.now()-lastMainCloseAt<700){event.preventDefault();event.stopPropagation();return;}
lastMainCloseAt=Date.now();
event.preventDefault();
event.stopPropagation();
if(event.stopImmediatePropagation) event.stopImmediatePropagation();
closeDialog();
}
listen(overlay,'pointerup',handleDelegatedMainClose,true);
listen(overlay,'click',handleDelegatedMainClose,true);
if(cameraButton) listen(cameraButton,'click',chooseCamera);
if(uploadButton) listen(uploadButton,'click',chooseUpload);
if(cameraCapture){var lastCameraShutterAt=0;var activateCameraShutter=function(event){var now=Date.now();if(event&&event.type==='click'&&now-lastCameraShutterAt<700){event.preventDefault();event.stopPropagation();return;}if(event){event.preventDefault();event.stopPropagation();}lastCameraShutterAt=now;captureRearCamera();};if(window.PointerEvent) listen(cameraCapture,'pointerdown',activateCameraShutter,{passive:false});else listen(cameraCapture,'touchstart',activateCameraShutter,{passive:false});listen(cameraCapture,'click',activateCameraShutter,{passive:false});}
if(cameraLibrary){listen(cameraLibrary,'click',chooseUploadFromCamera,{passive:false});}if(window.visualViewport){listen(window.visualViewport,'resize',syncLiveCameraViewport,{passive:true});listen(window.visualViewport,'scroll',syncLiveCameraViewport,{passive:true});}listen(window,'resize',syncLiveCameraViewport,{passive:true});listen(window,'orientationchange',syncLiveCameraViewport,{passive:true});listen(document,'fullscreenchange',syncLiveCameraViewport,{passive:true});listen(document,'webkitfullscreenchange',syncLiveCameraViewport,{passive:true});
if(cameraVideo){listen(cameraVideo,'touchstart',beginCameraPinch,{passive:false});listen(cameraVideo,'touchmove',moveCameraPinch,{passive:false});listen(cameraVideo,'touchend',endCameraPinch,{passive:true});listen(cameraVideo,'touchcancel',endCameraPinch,{passive:true});}
function handleCameraClose(event){
if(event){event.preventDefault();event.stopPropagation();if(event.stopImmediatePropagation) event.stopImmediatePropagation();}
closeDialog();
return false;
}
if(cameraCancel){
cameraCancel.onclick=handleCameraClose;
listen(cameraCancel,'click',handleCameraClose,true);
listen(cameraCancel,'touchend',handleCameraClose,{capture:true,passive:false});
listen(cameraCancel,'pointerup',handleCameraClose,true);
}
if(retakeButton) listen(retakeButton,'click',function(event){event.preventDefault();returnToPhotoStart();});
if(resetButton) listen(resetButton,'click',function(event){
if(event){event.preventDefault();event.stopPropagation();}
if(!state.photoReady) return;
closeDownloadGate();
setShareNote('');


if(state.calibrationActive||state.awaitingMeasurement){
state.pointA=null;
state.pointB=null;
state.awaitingMeasurement=false;
state.calibrationActive=true;
state.referenceMeasurement=0;
state.scaleHelpDismissed=false;
if(referenceMeasurement) referenceMeasurement.value='';
stage.classList.add('is-calibrating');
artCanvas.hidden=true;
if(artFx) artFx.hidden=true;
hidePlacementGuide();
hideConfirmPrompt();
positionMeasurementVisuals();
requestArtworkEffectsSync();
if(tapInstruction) tapInstruction.hidden=true;
if(resetButton) resetButton.hidden=false;
renderScaleHelp();
setPreviewActionState();
updateStickyBuy();
return;
}


state.hasPlacedOnce=false;
invalidateConfirmation(false);
resetArtworkPosition();
clearCalibration(true);
root.classList.remove('sc-wall-v1--confirmed');
if(overlay) overlay.classList.remove('is-confirmed');
stage.classList.remove('is-confirmed');
if(saveWrap) saveWrap.hidden=true;
state.previewChipDismissed=false;
showQuickPreview();
updateStickyBuy();
scrollVisualizerTop();
});
if(quickPreviewButton) listen(quickPreviewButton,'click',showQuickPreview);
var lastScaleControlAt=0;
function handleScaleControl(event){
var closeTarget=event.target&&event.target.closest?event.target.closest('[data-sc-wall-scale-help-close]'):null;
var reopenTarget=event.target&&event.target.closest?event.target.closest('[data-sc-wall-scale-help-reopen]'):null;
if(!closeTarget&&!reopenTarget) return;
if(event.type==='click'&&Date.now()-lastScaleControlAt<700){event.preventDefault();event.stopPropagation();return;}
lastScaleControlAt=Date.now();
event.preventDefault();
event.stopPropagation();
if(closeTarget) closeScaleHelp();
else reopenScaleHelp();
}
listen(overlay,'pointerup',handleScaleControl,true);
listen(overlay,'click',handleScaleControl,true);
if(submitMeasurementButton) listen(submitMeasurementButton,'click',submitMeasurement);
if(confirmButton) listen(confirmButton,'click',handleConfirmPlacement);
var lastPreviewToolTouchAt=0;
function handlePreviewToolActivation(event){
var target=event.target&&event.target.closest?event.target.closest('[data-sc-wall-save],[data-sc-wall-share-preview]'):null;
if(!target||overlay.hidden||!overlay.contains(target)) return;
if(event.type==='click'&&Date.now()-lastPreviewToolTouchAt<700){event.preventDefault();event.stopPropagation();return;}
if(event.type==='touchend') lastPreviewToolTouchAt=Date.now();
event.preventDefault();
event.stopPropagation();
if(event.stopImmediatePropagation) event.stopImmediatePropagation();
if(target.hasAttribute('data-sc-wall-save')) requestDownloadPreview(event);
else if(target.hasAttribute('data-sc-wall-share-preview')) shareConfirmedPreview(event);
}
// Capture before theme document-level coordinate/search handlers, for these controls only.
listen(window,'touchend',handlePreviewToolActivation,{capture:true,passive:false});
listen(window,'click',handlePreviewToolActivation,true);
function shieldPreviewToolPointer(event){var target=event.target&&event.target.closest?event.target.closest('[data-sc-wall-save],[data-sc-wall-share-preview]'):null;if(target&&!overlay.hidden&&overlay.contains(target))event.stopImmediatePropagation();}
listen(window,'pointerdown',shieldPreviewToolPointer,true);
listen(window,'pointerup',shieldPreviewToolPointer,true);
if(downloadConfirm) listen(downloadConfirm,'click',downloadConfirmedPreview);
if(downloadClose) listen(downloadClose,'click',function(event){event.preventDefault();closeDownloadGate();});
if(downloadName) listen(downloadName,'keydown',function(event){if(event.key==='Enter'){event.preventDefault();if(downloadEmail) downloadEmail.focus();}});
if(downloadEmail) listen(downloadEmail,'keydown',function(event){if(event.key==='Enter'){event.preventDefault();downloadConfirmedPreview();}});
if(previewChip) listen(previewChip,'click',function(event){event.preventDefault();event.stopPropagation();setTrueScaleFromQuick();});
if(stickySecure) listen(stickySecure,'click',addSelectedVariantToCart);
if(cameraInput) listen(cameraInput,'change',function(){if(cameraInput.files&&cameraInput.files[0]){if(overlay.hidden) showDialog();activatePhoto(cameraInput.files[0]);}else if(overlay.hidden){restorePagePosition();}});
if(uploadInput) listen(uploadInput,'change',function(){if(uploadInput.files&&uploadInput.files[0]){if(cameraStream||!liveCamera.hidden) stopLiveCamera();if(overlay.hidden) showDialog();activatePhoto(uploadInput.files[0]);}else if(overlay.hidden){restorePagePosition();}});
sizeButtons.forEach(function(button){listen(button,'click',function(){selectSizeButton(button,true,true);setStickyCartState();});});
if(referenceMeasurement){
listen(referenceMeasurement,'keydown',function(event){if(event.key==='Enter'){event.preventDefault();submitMeasurement();}});
listen(referenceMeasurement,'input',function(){setFlowError('');});
listen(referenceMeasurement,'pointerdown',function(event){event.stopPropagation();});
listen(referenceMeasurement,'touchstart',function(event){event.stopPropagation();},{passive:true});
listen(referenceMeasurement,'click',function(event){event.stopPropagation();try{referenceMeasurement.focus({preventScroll:true});}catch(error){referenceMeasurement.focus();}});
}
if(scaleHelp){
listen(scaleHelp,'pointerdown',function(event){event.stopPropagation();});
listen(scaleHelp,'touchstart',function(event){event.stopPropagation();},{passive:true});
listen(scaleHelp,'click',function(event){event.stopPropagation();});
}
if(landscapeScaleDock){
listen(landscapeScaleDock,'click',function(event){if(event.target===landscapeScaleDock&&scaleHelp&&!scaleHelp.hidden) closeScaleHelp();});
}

listen(stage,'pointerdown',stageCalibrationTap);
listen(artCanvas,'pointerdown',beginDrag);listen(artCanvas,'pointermove',moveDrag);listen(artCanvas,'pointerup',endDrag);listen(artCanvas,'pointercancel',endDrag);listen(artCanvas,'lostpointercapture',endDrag);
listen(modal,'scroll',updateStickyBuy,{passive:true});
listen(overlay,'click',function(event){if(downloadGate&&event.target===downloadGate){event.preventDefault();closeDownloadGate();return;}if(event.target===overlay){event.preventDefault();closeDialog();}});
listen(document,'keydown',function(event){if(!overlay.hidden&&event.key==='Tab'){var scope=downloadGate&&!downloadGate.hidden?downloadGate:liveCamera&&!liveCamera.hidden?liveCamera:overlay;var items=Array.from(scope.querySelectorAll('button:not([disabled]),input:not([disabled]),select,a[href],[tabindex="0"]')).filter(function(e){return e.getClientRects().length;});var first=items[0],last=items[items.length-1];if(first&&(!scope.contains(document.activeElement)||(event.shiftKey&&document.activeElement===first)||(!event.shiftKey&&document.activeElement===last))){event.preventDefault();(event.shiftKey?last:first).focus();}}if(event.key!=='Escape'||overlay.hidden) return;event.preventDefault();if(downloadGate&&!downloadGate.hidden){closeDownloadGate();return;}closeDialog();});

function closeCartDrawerFromBackdrop(event){if(!event||!event.target||!event.target.closest) return;var backdrop=event.target.closest('[data-sc-cart-backdrop],.sc-cart-backdrop,[data-drawer-overlay]');if(!backdrop) return;var drawer=cartDrawer();if(!drawer||drawer.getAttribute('aria-hidden')==='true') return;try{document.dispatchEvent(new CustomEvent('dispatch:cart-drawer:close',{bubbles:true,detail:{source:'sports-cave-wall-visualizer'}}));}catch(error){}try{if(typeof drawer.close==='function') drawer.close();}catch(error){}window.setTimeout(clearCartLayerIfClosed,180);}
listen(document,'click',closeCartDrawerFromBackdrop,false);
listen(document,'cart:close',function(){window.setTimeout(clearCartLayerIfClosed,40);});
listen(document,'dispatch:cart-drawer:close',function(){window.setTimeout(clearCartLayerIfClosed,40);});

listen(document,'change',function(event){var input=event.target;if(!input||!input.matches||!input.matches('variant-picker.sc-vp input[type="radio"]')) return;var picker=input.closest('variant-picker.sc-vp');if(picker!==productPickerFor(root)) return;var group=input.closest('.option-selector');var optionName=group?String(group.getAttribute('data-option')||'').toLowerCase():'';if(optionName.indexOf('frame')>-1||optionName.indexOf('style')>-1){savedBlob=null;assetRevision+=1;assetPromise=null;savedFile=null;if(state.confirmed) invalidateConfirmation(true);state.frame=currentFrameFromPicker(root);if(state.photoReady) drawArtwork().then(function(){if(state.quickPreview) applyQuickPreviewSize();else if(state.calibrated) applyScaledSize();});updateStatus();}if(optionName.indexOf('size')>-1){var button=findButtonForRaw(input.value);syncSizeAvailabilityFromPicker();if(button&&!button.disabled) selectSizeButton(button,false,false);if(!state.confirmed&&previewIsReady()&&!artCanvas.hidden){showPlacementGuide();showConfirmPrompt(120);}}updateStatus();setPreviewActionState();setStickyCartState();});

function measurementInputActive(){return !!(referenceMeasurement&&document.activeElement===referenceMeasurement&&state.awaitingMeasurement);}
var resizeTimer=0;listen(window,'resize',function(){window.clearTimeout(resizeTimer);resizeTimer=window.setTimeout(function(){if(measurementInputActive()) return;applyDeviceMode();syncLandscapeControls();syncLandscapeScaleDock();positionMeasurementVisuals();if(state.quickPreview) applyQuickPreviewSize();else if(state.calibrated) applyScaledSize();requestArtworkEffectsSync();updateStickyBuy();syncDesktopPreviewLayout();},80);},{passive:true});listen(window,'orientationchange',function(){window.setTimeout(function(){if(measurementInputActive()) return;applyDeviceMode();syncLandscapeControls();syncLandscapeScaleDock();positionMeasurementVisuals();if(state.quickPreview) applyQuickPreviewSize();else if(state.calibrated) applyScaledSize();requestArtworkEffectsSync();updateStickyBuy();syncDesktopPreviewLayout();},140);},{passive:true});
listen(document,'visibilitychange',function(){if(document.hidden&&liveCamera&&!liveCamera.hidden)cancelRearCamera();});
listen(window,'beforeunload',function(){stopLiveCamera();if(objectUrl) URL.revokeObjectURL(objectUrl);},{once:true});
if(openImmediately) launchWallExperience();
}

function bind(root){if(!root||root.getAttribute('data-sc-wall-bound')==='1'||root.getAttribute('data-sc-wall-initialized')==='1') return;var openButton=root.querySelector('[data-sc-wall-open]');if(!openButton) return;root.setAttribute('data-sc-wall-bound','1');openButton.addEventListener('click',function firstOpen(event){event.preventDefault();root.removeAttribute('data-sc-wall-bound');init(root,true);},{once:true});}
function boot(){document.querySelectorAll(ROOT_SELECTOR).forEach(bind);}
boot();
if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot,{once:true});
document.addEventListener('shopify:section:load',boot);
document.addEventListener('shopify:section:unload',function(event){event.target.querySelectorAll(ROOT_SELECTOR).forEach(function(root){if(root.scWallDestroy)root.scWallDestroy();});});
}());
