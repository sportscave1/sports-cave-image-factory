(function(){
'use strict';
if(window.__scWallPreviewInstalled)return;window.__scWallPreviewInstalled=true;
var api=window.SportsCaveWallArtwork,h=api.helpers,renderProductArtwork=api.render;
var ROOT_SELECTOR='[data-sc-wall-root]';
var clamp=h.clamp;
var clean=h.clean;
var makeId=h.makeId;
var browserSessionId=h.browserSessionId;
var frameName=h.frameName;
var parseSizeInfo=h.parseSizeInfo;
var formatSize=h.formatSize;
var currentFrameFromPicker=h.currentFrameFromPicker;
var currentSizeFromPicker=h.currentSizeFromPicker;
var currentUnitFromPicker=h.currentUnitFromPicker;
var productPickerFor=h.productPickerFor;
var loadImage=h.loadImage;
function init(root){
if(!root||root.scWallOpen||!root.querySelector('[data-sc-wall-overlay]'))return;
var detach=[];function listen(target,type,handler,options){if(!target)return;target.addEventListener(type,handler,options);detach.push(function(){target.removeEventListener(type,handler,options);});}
var overlay=root.querySelector('[data-sc-wall-overlay]');

var modal=root.querySelector('[data-sc-wall-modal]');

var closeButton=root.querySelector('[data-sc-wall-close]');

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

var deviceNote=root.querySelector('[data-sc-wall-device-note]');
var intro=root.querySelector('[data-sc-wall-intro]');
var editor=root.querySelector('[data-sc-wall-editor]');
var stage=root.querySelector('[data-sc-wall-stage]');

var roomImage=root.querySelector('[data-sc-wall-room]');
var artCanvas=root.querySelector('[data-sc-wall-art]');
var artError=root.querySelector('[data-sc-wall-art-error]');
var artRetry=root.querySelector('[data-sc-wall-art-retry]');
var artFx=root.querySelector('[data-sc-wall-art-fx]');




















var stickyBuy=root.querySelector('[data-sc-wall-sticky-buy]');
var keepBrowsing=root.querySelector('[data-sc-wall-keep-browsing]');








var sizeButtons=Array.prototype.slice.call(root.querySelectorAll('[data-sc-wall-size-option]'));
























var stickySecure=root.querySelector('[data-sc-wall-sticky-secure]'),stickyCartLabel=root.querySelector('[data-sc-wall-cart-label]'),stickyCartPrice=root.querySelector('[data-sc-wall-cart-price]'),stickyCartError=root.querySelector('[data-sc-wall-cart-error]');
var scaleHelp=root.querySelector('[data-sc-wall-scale-help]'),scaleEntry=root.querySelector('[data-sc-wall-scale-entry]'),referenceMeasurement=root.querySelector('[data-sc-wall-reference-measurement]'),measurementUnit=root.querySelector('[data-sc-wall-measurement-unit]'),flowError=root.querySelector('[data-sc-wall-flow-error]'),pointAEl=root.querySelector('[data-sc-wall-point-a]'),pointBEl=root.querySelector('[data-sc-wall-point-b]'),measureLine=root.querySelector('[data-sc-wall-measure-line]');
var calibrationSnapshot=null,dialogSession=0,cartBusy=false,cartAddedUntil=0,cartSuccessTimer=0;
var skipScale=root.querySelector("[data-sc-wall-skip-scale]");
var tapDemo=root.querySelector('[data-sc-wall-tap-demo]'),scaleCancel=root.querySelector('[data-sc-wall-scale-cancel]');
var scaleStatus=root.querySelector('[data-sc-wall-scale-status]'),scaleCopy=root.querySelector('[data-sc-wall-scale-copy]'),scaleStart=root.querySelector('[data-sc-wall-scale-start]');
var saveWrap=root.querySelector('[data-sc-wall-save-wrap]'),saveButton=root.querySelector('[data-sc-wall-save]'),sharePreviewButton=root.querySelector('[data-sc-wall-share-preview]'),shareNote=root.querySelector('[data-sc-wall-share-note]');
var downloadGate=root.querySelector('[data-sc-wall-download-gate]'),downloadName=root.querySelector('[data-sc-wall-download-name]'),downloadEmail=root.querySelector('[data-sc-wall-download-email]'),downloadConsent=root.querySelector('[data-sc-wall-download-consent]'),downloadError=root.querySelector('[data-sc-wall-download-error]'),downloadConfirm=root.querySelector('[data-sc-wall-download-confirm]');
var saveLabel=null,sharePreviewLabel=null,frameLabel=null,sizeSummary=null,scaleUnitInline=null,tapInstruction=null,initialScalePrompt=true;

var productData={options:[],variants:[]};
var productDataNode=root.querySelector('[data-sc-wall-product-data]');
if(productDataNode){try{productData=JSON.parse(productDataNode.textContent||'{}')||productData;}catch(error){}}
var PRODUCT_OPTS=Array.isArray(productData.options)?productData.options:[];
var VARIANTS=Array.isArray(productData.variants)?productData.variants:[];


var FORMATTED=productData.formatted||{};
var context=artCanvas.getContext('2d');

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

var cameraArtworkPrimePromise=null;
var photoLoadSeq=0;
var lastActiveElement=null;

var confirmTimer=0,archivePromise=null,lastArchiveBlob=null;var sessionId=browserSessionId();var state={frame:currentFrameFromPicker(root),unit:currentUnitFromPicker(root)||(root.getAttribute('data-unit')==='in'?'in':'cm'),sizeRaw:'',sizeInfo:null,photoReady:false,calibrated:false,calibrationActive:false,awaitingMeasurement:false,referenceMeasurement:0,pointA:null,pointB:null,centerX:50,centerY:44,artWidthPercent:42,dragging:false,dragPointerId:null,dragStartX:0,dragStartY:0,dragStartCenterX:50,dragStartCenterY:44,pageScrollX:0,pageScrollY:0,isMobileCamera:false,previewChipDismissed:false,upsizeCueArmed:false,upsizeCueConsumed:false,upsizeCueTargetRaw:'',clientPreviewId:makeId('preview'),previewId:'',shareUrl:'',storageSaved:false,storageAccepted:false,archiveStatus:'',confirmed:false,confirming:false,confirmPromptReady:false,hasDraggedPlacement:false,quickPreview:false,scaleHelpDismissed:false,hasPlacedOnce:false,photoLandscape:false,startedAt:new Date().toISOString()};


var DOWNLOAD_IDENTITY_KEY='sc_wall_preview_download_identity_v1',artworkRenderRevision=0;
function sourceUrlFor(frame){return root.getAttribute('data-'+(frame==='unframed'?'black':frame)+'-url')||root.getAttribute('data-black-url')||'';}
function loggedInIdentity(){var email=String(root.getAttribute('data-customer-email')||'').trim().toLowerCase();var name=String(root.getAttribute('data-customer-name')||'').trim();var customerId=String(root.getAttribute('data-customer-id')||'').trim();if(!email&&!customerId) return null;return {email:email,name:name,shopifyCustomerId:customerId,source:'logged_in'};}
function validIdentityEmail(value){return /^[^\s@\/\\]+@[^\s@\/\\]+\.[^\s@\/\\]+$/.test(String(value||'').trim());}
function sessionDownloadIdentity(){try{var raw=window.sessionStorage.getItem(DOWNLOAD_IDENTITY_KEY);if(!raw) return null;var parsed=JSON.parse(raw);var email=String(parsed&&parsed.email||'').trim().toLowerCase();var name=clean(parsed&&parsed.name||'');if(!validIdentityEmail(email)) return null;return {email:email,name:name,shopifyCustomerId:'',source:'guest'};}catch(error){return null;}}
function attributionParams(){var out={referrer:document.referrer||'',landing_url:window.location.href,utm_source:'',utm_medium:'',utm_campaign:'',utm_content:'',utm_term:''};try{var url=new URL(window.location.href);['utm_source','utm_medium','utm_campaign','utm_content','utm_term'].forEach(function(key){out[key]=url.searchParams.get(key)||'';});}catch(error){}return out;}
function isMobileCameraDevice(){var ua=navigator.userAgent||'';var touch=Number(navigator.maxTouchPoints||0)>0;var coarse=false;try{coarse=window.matchMedia&&window.matchMedia('(pointer: coarse)').matches;}catch(error){}return /Android|iPhone|iPad|iPod/i.test(ua)||(touch&&coarse);}
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
function sampleRoomAverage(x,y,w,h){try{if(!roomImage||!roomImage.naturalWidth||!roomImage.naturalHeight) return null;var sx=Math.max(0,Math.round(x));var sy=Math.max(0,Math.round(y));var sw=Math.max(4,Math.round(w));var sh=Math.max(4,Math.round(h));if(sx>=roomImage.naturalWidth||sy>=roomImage.naturalHeight) return null;sw=Math.min(sw,roomImage.naturalWidth-sx);sh=Math.min(sh,roomImage.naturalHeight-sy);var canvas=document.createElement('canvas');canvas.width=24;canvas.height=24;var ctx=canvas.getContext('2d',{willReadFrequently:true});if(!ctx) return null;ctx.drawImage(roomImage,sx,sy,sw,sh,0,0,24,24);var data=ctx.getImageData(0,0,24,24).data;var r=0,g=0,b=0,c=0;for(var i=0;i<data.length;i+=4){if(data[i+3]<12) continue;r+=data[i];g+=data[i+1];b+=data[i+2];c++;}if(!c) return null;return {r:r/c,g:g/c,b:b/c};}catch(error){return null;}}
function liveArtworkLighting(){if(!roomImage||!roomImage.naturalWidth||!roomImage.naturalHeight||!artCanvas||artCanvas.hidden) return null;var artW=roomImage.naturalWidth*(state.artWidthPercent/100);var artH=artCanvas.width&&artCanvas.height?artW*(artCanvas.height/artCanvas.width):artW*0.75;var x=roomImage.naturalWidth*(state.centerX/100)-artW/2;var y=roomImage.naturalHeight*(state.centerY/100)-artH/2;var padX=Math.max(12,artW*.08);var padY=Math.max(12,artH*.08);var top=sampleRoomAverage(x+artW*.16,Math.max(0,y-padY),artW*.68,padY);var left=sampleRoomAverage(Math.max(0,x-padX),y+artH*.18,padX,artH*.64);var right=sampleRoomAverage(Math.min(roomImage.naturalWidth-4,x+artW),y+artH*.18,padX,artH*.64);var bottom=sampleRoomAverage(x+artW*.16,Math.min(roomImage.naturalHeight-4,y+artH),artW*.68,padY);var ambient=top||left||right||bottom;if(!ambient) return null;var luma=.2126*ambient.r+.7152*ambient.g+.0722*ambient.b;return {ambient:ambient,luma:luma,top:top,left:left,right:right,bottom:bottom};}
function applyLiveArtworkPhotorealism(){var lighting=liveArtworkLighting();if(!lighting||!stage) return;var warm=((lighting.ambient.r-lighting.ambient.b)/255);var bright=clamp((lighting.luma-122)/255,-.18,.18);stage.style.setProperty('--sc-art-ambient-rgb',Math.round(lighting.ambient.r)+','+Math.round(lighting.ambient.g)+','+Math.round(lighting.ambient.b));stage.style.setProperty('--sc-art-brightness',(0.988+bright*.16).toFixed(3));stage.style.setProperty('--sc-art-contrast',(0.992+bright*.04).toFixed(3));stage.style.setProperty('--sc-art-saturation',(0.99+Math.max(-.02,Math.min(.02,warm*.14))).toFixed(3));stage.style.setProperty('--sc-art-shadow-blur',Math.max(10,Math.round((artCanvas.getBoundingClientRect().width||100)*.055))+'px');stage.style.setProperty('--sc-art-shadow-y',Math.max(5,Math.round((artCanvas.getBoundingClientRect().width||100)*.02))+'px');stage.style.setProperty('--sc-art-shadow-alpha',(0.11+Math.max(0,.14-bright*.18)).toFixed(3));stage.style.setProperty('--sc-art-shadow-alpha-soft',(0.075+Math.max(0,.08-bright*.12)).toFixed(3));stage.style.setProperty('--sc-art-fx-opacity',(0.58+Math.max(0,bright*.12)).toFixed(3));stage.style.setProperty('--sc-art-glare-strong',(0.06+Math.max(0,bright*.1)).toFixed(3));stage.style.setProperty('--sc-art-glare-soft',(0.02+Math.max(0,bright*.04)).toFixed(3));stage.style.setProperty('--sc-art-ambient-alpha',(0.028+Math.abs(warm)*.035).toFixed(3));stage.style.setProperty('--sc-art-border-alpha',(0.028+Math.max(0,bright*.03)).toFixed(3));}
function requestArtworkEffectsSync(){window.requestAnimationFrame(syncArtworkEffects);}
function drawArtwork(){

 state.frame=currentFrameFromPicker(root);var revision=++artworkRenderRevision;

 return renderProductArtwork(root,state.frame).then(function(rendered){

  if(revision!==artworkRenderRevision||overlay.hidden)return;

  state.artworkFailed=false;if(artError)artError.hidden=true;

  artCanvas.width=rendered.width;artCanvas.height=rendered.height;

  context.clearRect(0,0,artCanvas.width,artCanvas.height);context.drawImage(rendered,0,0);

  stage.setAttribute('data-sc-art-frame',state.frame);

  invalidateComposite();requestArtworkEffectsSync();if(state.calibrated)applyScaledSize();else if(state.quickPreview)applyQuickPreviewSize();setPreviewActionState();updateStickyBuy();

 }).catch(function(){

  if(revision!==artworkRenderRevision||overlay.hidden)return;

  state.artworkFailed=true;artCanvas.hidden=true;if(artError)artError.hidden=false;

  context.clearRect(0,0,artCanvas.width,artCanvas.height);requestArtworkEffectsSync();setPreviewActionState();updateStickyBuy();

 });

}
function applyArtworkPosition(){artCanvas.style.left=state.centerX+'%';artCanvas.style.top=state.centerY+'%';requestArtworkEffectsSync();}
function cameraTouchDistance(touches){if(!touches||touches.length<2) return 0;var dx=touches[0].clientX-touches[1].clientX;var dy=touches[0].clientY-touches[1].clientY;return Math.sqrt(dx*dx+dy*dy);}
function configureCameraZoom(){cameraTrack=cameraStream&&cameraStream.getVideoTracks?cameraStream.getVideoTracks()[0]:null;cameraNativeZoom=false;cameraZoomMin=1;cameraZoomMax=3;cameraZoomValue=1;if(cameraTrack&&typeof cameraTrack.getCapabilities==='function'){try{var capabilities=cameraTrack.getCapabilities()||{};if(capabilities.zoom&&Number.isFinite(capabilities.zoom.min)&&Number.isFinite(capabilities.zoom.max)){cameraNativeZoom=true;cameraZoomMin=Number(capabilities.zoom.min);cameraZoomMax=Math.min(Number(capabilities.zoom.max),5);var settings=typeof cameraTrack.getSettings==='function'?cameraTrack.getSettings():{};cameraZoomValue=Number.isFinite(settings.zoom)?clamp(Number(settings.zoom),cameraZoomMin,cameraZoomMax):cameraZoomMin;}}catch(error){cameraNativeZoom=false;}}if(!cameraNativeZoom){cameraZoomMin=1;cameraZoomMax=3;cameraZoomValue=1;}cameraPendingZoom=cameraZoomValue;if(cameraVideo){cameraVideo.style.transform=cameraNativeZoom?'scale(1)':'scale('+cameraZoomValue+')';cameraVideo.style.transformOrigin='50% 50%';}}
async function applyBestCameraImageSettings(){if(!cameraTrack||typeof cameraTrack.getCapabilities!=='function'||typeof cameraTrack.applyConstraints!=='function') return;try{var caps=cameraTrack.getCapabilities()||{};var advanced={};if(Array.isArray(caps.focusMode)&&caps.focusMode.indexOf('continuous')>-1) advanced.focusMode='continuous';if(Array.isArray(caps.exposureMode)&&caps.exposureMode.indexOf('continuous')>-1) advanced.exposureMode='continuous';if(Array.isArray(caps.whiteBalanceMode)&&caps.whiteBalanceMode.indexOf('continuous')>-1) advanced.whiteBalanceMode='continuous';if(caps.exposureCompensation&&Number.isFinite(caps.exposureCompensation.min)&&Number.isFinite(caps.exposureCompensation.max)){advanced.exposureCompensation=clamp(0.25,Number(caps.exposureCompensation.min),Number(caps.exposureCompensation.max));}if(Object.keys(advanced).length){await cameraTrack.applyConstraints({advanced:[advanced]});}}catch(error){}}
async function setCameraZoom(next){next=clamp(Number(next)||cameraZoomMin,cameraZoomMin,cameraZoomMax);cameraZoomValue=next;if(cameraNativeZoom&&cameraTrack&&typeof cameraTrack.applyConstraints==='function'){try{await cameraTrack.applyConstraints({advanced:[{zoom:cameraZoomValue}]});var settings=typeof cameraTrack.getSettings==='function'?cameraTrack.getSettings():{};if(Number.isFinite(settings.zoom)) cameraZoomValue=Number(settings.zoom);if(cameraVideo) cameraVideo.style.transform='scale(1)';return;}catch(error){cameraNativeZoom=false;cameraZoomMin=1;cameraZoomMax=3;cameraZoomValue=clamp(next,1,3);}}if(cameraVideo){cameraVideo.style.transform='scale('+cameraZoomValue+')';cameraVideo.style.transformOrigin='50% 50%';}}
function beginCameraPinch(event){if(!cameraVideo||!cameraStream||!event.touches||event.touches.length!==2) return;cameraPinchStartDistance=cameraTouchDistance(event.touches);cameraPinchStartZoom=cameraZoomValue;if(cameraPinchStartDistance>0) event.preventDefault();}
function moveCameraPinch(event){if(!cameraVideo||!cameraStream||!event.touches||event.touches.length!==2||!cameraPinchStartDistance) return;event.preventDefault();var distance=cameraTouchDistance(event.touches);if(!distance) return;cameraPendingZoom=clamp(cameraPinchStartZoom*(distance/cameraPinchStartDistance),cameraZoomMin,cameraZoomMax);if(cameraZoomRaf) return;cameraZoomRaf=window.requestAnimationFrame(function(){cameraZoomRaf=0;setCameraZoom(cameraPendingZoom);});}
function endCameraPinch(event){if(!event.touches||event.touches.length<2){cameraPinchStartDistance=0;cameraPinchStartZoom=cameraZoomValue;}}
function cameraVisibleRatio(){

var rect=cameraShell&&cameraShell.getBoundingClientRect?cameraShell.getBoundingClientRect():null;

if(rect&&rect.width>1&&rect.height>1) return rect.width/rect.height;

var viewportW=Math.max(1,window.innerWidth||document.documentElement.clientWidth||1),viewportH=Math.max(1,window.innerHeight||document.documentElement.clientHeight||1);

return viewportW/viewportH;

}
function cameraTargetRatio(){return cameraVisibleRatio();}
function cameraCropRect(sourceW,sourceH){var targetRatio=cameraTargetRatio();var cropW=sourceW,cropH=sourceH;if(sourceW/sourceH>targetRatio){cropW=sourceH*targetRatio;}else{cropH=sourceW/targetRatio;}var digitalZoom=cameraNativeZoom?1:Math.max(1,cameraZoomValue);cropW/=digitalZoom;cropH/=digitalZoom;return {x:(sourceW-cropW)/2,y:(sourceH-cropH)/2,w:cropW,h:cropH};}
function freezeVisibleCameraFrame(){if(!cameraVideo||!cameraVideo.videoWidth||!cameraVideo.videoHeight) return null;try{var crop=cameraCropRect(cameraVideo.videoWidth,cameraVideo.videoHeight);var canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(crop.w));canvas.height=Math.max(1,Math.round(crop.h));var ctx=canvas.getContext('2d');if(!ctx) return null;ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(cameraVideo,crop.x,crop.y,crop.w,crop.h,0,0,canvas.width,canvas.height);return canvas;}catch(error){return null;}}
function cameraAutoEnhanceFilter(source,crop){var fallback='brightness(1.07) contrast(1.025) saturate(1.055)';try{var sample=document.createElement('canvas');sample.width=48;sample.height=48;var sampleCtx=sample.getContext('2d',{willReadFrequently:true});if(!sampleCtx) return fallback;sampleCtx.drawImage(source,crop.x,crop.y,crop.w,crop.h,0,0,48,48);var pixels=sampleCtx.getImageData(0,0,48,48).data;var total=0,count=0;for(var i=0;i<pixels.length;i+=4){if(pixels[i+3]<16) continue;var luma=.2126*pixels[i]+.7152*pixels[i+1]+.0722*pixels[i+2];if(luma<5||luma>250) continue;total+=luma;count+=1;}var average=count?total/count:135;var brightness=average<82?1.14:(average<108?1.11:(average<138?1.085:(average<170?1.06:1.035)));var contrast=average<105?1.04:(average<155?1.03:1.02);var saturation=average<95?1.065:1.055;return 'brightness('+brightness.toFixed(3)+') contrast('+contrast.toFixed(3)+') saturate('+saturation.toFixed(3)+')';}catch(error){return fallback;}}
function renderCameraSourceToBlob(source,sourceW,sourceH,alreadyCropped){return new Promise(function(resolve,reject){try{var crop=alreadyCropped?{x:0,y:0,w:sourceW,h:sourceH}:cameraCropRect(sourceW,sourceH);var maxDim=3840,maxPixels=12000000;var outScale=Math.min(1,maxDim/crop.w,maxDim/crop.h,Math.sqrt(maxPixels/(crop.w*crop.h)));var capture=document.createElement('canvas');capture.width=Math.max(1,Math.round(crop.w*outScale));capture.height=Math.max(1,Math.round(crop.h*outScale));var captureContext=capture.getContext('2d');if(!captureContext){reject(new Error('Camera canvas unavailable'));return;}captureContext.imageSmoothingEnabled=true;captureContext.imageSmoothingQuality='high';captureContext.filter=cameraAutoEnhanceFilter(source,crop);captureContext.drawImage(source,crop.x,crop.y,crop.w,crop.h,0,0,capture.width,capture.height);captureContext.filter='none';capture.toBlob(function(blob){if(blob) resolve(blob);else reject(new Error('Camera image unavailable'));},'image/jpeg',.97);}catch(error){reject(error);}});}
function clearCaptureFreeze(){if(captureFreezeCanvas&&captureFreezeCanvas.parentNode){try{captureFreezeCanvas.parentNode.removeChild(captureFreezeCanvas);}catch(error){}}captureFreezeCanvas=null;}
function primeCameraArtwork(){if(!state.isMobileCamera) return;syncFromProductPage(true);artCanvas.hidden=true;cameraArtworkPrimePromise=drawArtwork().catch(function(){return null;});}
function stopLiveCamera(){cameraRequestGeneration+=1;if(cameraZoomRaf){window.cancelAnimationFrame(cameraZoomRaf);cameraZoomRaf=0;}if(cameraHintTimer){window.clearTimeout(cameraHintTimer);cameraHintTimer=0;}if(cameraHint) cameraHint.hidden=true;cameraPinchStartDistance=0;cameraPinchStartZoom=1;cameraPendingZoom=1;cameraImageCapture=null;cameraCaptureBusy=false;if(cameraCapture){cameraCapture.disabled=false;cameraCapture.removeAttribute('aria-busy');cameraCapture.classList.remove('is-shooting');}if(cameraStream){cameraStream.getTracks().forEach(function(track){try{track.stop();}catch(error){}});cameraStream=null;}cameraTrack=null;cameraNativeZoom=false;cameraZoomValue=1;cameraZoomMin=1;cameraZoomMax=3;if(cameraVideo){try{cameraVideo.pause();}catch(error){}cameraVideo.srcObject=null;cameraVideo.style.transform='scale(1)';}if(liveCamera) liveCamera.hidden=true;}
async function startRearCamera(){if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){intro.hidden=false;editor.hidden=true;if(deviceNote){deviceNote.textContent='Camera unavailable. You can choose a wall photo instead.';deviceNote.hidden=false;}if(state.isMobileCamera&&cameraInput){cameraInput.value='';cameraInput.click();}return;}stopLiveCamera();var requestGeneration=cameraRequestGeneration,openedStream=null;if(!cameraArtworkPrimePromise)primeCameraArtwork();if(overlay) overlay.classList.remove('is-photo-ready');if(stickyBuy) stickyBuy.hidden=true;if(modal) modal.classList.remove('has-sticky-buy');if(liveCamera) liveCamera.hidden=false;intro.hidden=true;editor.hidden=true;var baseVideo={facingMode:{ideal:'environment'},width:{ideal:4096},height:{ideal:2160},frameRate:{ideal:24,max:30}};var exactVideo={facingMode:{exact:'environment'},width:{ideal:4096},height:{ideal:2160},frameRate:{ideal:24,max:30}};try{try{openedStream=await navigator.mediaDevices.getUserMedia({audio:false,video:exactVideo});}catch(firstError){if(requestGeneration!==cameraRequestGeneration||firstError.name==='NotAllowedError'||firstError.name==='SecurityError')throw firstError;openedStream=await navigator.mediaDevices.getUserMedia({audio:false,video:baseVideo});}if(requestGeneration!==cameraRequestGeneration||overlay.hidden){openedStream.getTracks().forEach(function(t){t.stop();});return;}cameraStream=openedStream;if(cameraVideo){cameraVideo.srcObject=cameraStream;await cameraVideo.play();engagement.source('camera');engagement.event('wall_preview_camera_open');if(cameraHint){cameraHint.hidden=false;if(cameraHintTimer) window.clearTimeout(cameraHintTimer);cameraHintTimer=window.setTimeout(function(){if(cameraHint) cameraHint.hidden=true;cameraHintTimer=0;},4200);}configureCameraZoom();await applyBestCameraImageSettings();try{if(cameraTrack&&typeof ImageCapture!=='undefined') cameraImageCapture=new ImageCapture(cameraTrack);}catch(imageCaptureError){cameraImageCapture=null;}}}catch(error){if(requestGeneration!==cameraRequestGeneration)return;stopLiveCamera();if(deviceNote){deviceNote.textContent="Camera unavailable. You can choose a wall photo instead.";deviceNote.hidden=false;}if(state.photoReady){editor.hidden=false;setStagePhotoState();}else{intro.hidden=false;}if(state.isMobileCamera&&cameraInput){cameraInput.value='';cameraInput.click();}}}
function captureRearCamera(){if(cameraCaptureBusy||!cameraVideo||!cameraVideo.videoWidth||!cameraVideo.videoHeight)return;if(cameraHintTimer){window.clearTimeout(cameraHintTimer);cameraHintTimer=0;}if(cameraHint)cameraHint.hidden=true;var captureSeq=++cameraCaptureSeq;cameraCaptureBusy=true;if(cameraCapture){cameraCapture.disabled=true;cameraCapture.setAttribute('aria-busy','true');cameraCapture.classList.add('is-shooting');}var frozen=freezeVisibleCameraFrame();if(!frozen){cameraCaptureBusy=false;if(cameraCapture){cameraCapture.disabled=false;cameraCapture.removeAttribute('aria-busy');cameraCapture.classList.remove('is-shooting');}return;}try{cameraVideo.pause();}catch(error){}showCaptureFreeze(frozen);stopLiveCamera();cameraCaptureBusy=true;renderCameraSourceToBlob(frozen,frozen.width,frozen.height,true).then(function(blob){if(captureSeq!==cameraCaptureSeq)return;stopLiveCamera();if(!blob)throw new Error('Camera image unavailable');activatePhoto(blob,true);}).catch(function(){if(captureSeq!==cameraCaptureSeq)return;stopLiveCamera();try{frozen.toBlob(function(blob){if(captureSeq!==cameraCaptureSeq)return;if(blob)activatePhoto(blob,true);else returnToPhotoStart();},'image/jpeg',.97);}catch(error){if(captureSeq===cameraCaptureSeq)returnToPhotoStart();}});}
function chooseUpload(){stopLiveCamera();if(!uploadInput) return;if(deviceNote) deviceNote.hidden=true;uploadInput.value='';uploadInput.click();}
function chooseUploadFromCamera(event){if(event){event.preventDefault();event.stopPropagation();}if(!uploadInput) return;if(cameraHintTimer){window.clearTimeout(cameraHintTimer);cameraHintTimer=0;}if(cameraHint) cameraHint.hidden=true;uploadInput.value='';uploadInput.click();}
function rememberPagePosition(){state.pageScrollX=window.scrollX||window.pageXOffset||0;state.pageScrollY=window.scrollY||window.pageYOffset||0;}
function restorePagePosition(){var x=state.pageScrollX,y=state.pageScrollY;window.requestAnimationFrame(function(){window.scrollTo(x,y);window.setTimeout(function(){window.scrollTo(x,y);},40);});}
async function buildCompositeCanvas(includeBrandOverlay,maxDimOverride,maxPixelsOverride){if(typeof includeBrandOverlay==='undefined') includeBrandOverlay=true;if(!state.photoReady||!previewIsReady()||artCanvas.hidden||!roomImage.naturalWidth||!roomImage.naturalHeight) throw new Error('Preview is not ready');var sourceW=roomImage.naturalWidth,sourceH=roomImage.naturalHeight,maxDim=Number(maxDimOverride)||6000,maxPixels=Number(maxPixelsOverride)||24000000;var scale=Math.min(1,maxDim/sourceW,maxDim/sourceH,Math.sqrt(maxPixels/(sourceW*sourceH)));var output=document.createElement('canvas');output.width=Math.max(1,Math.round(sourceW*scale));output.height=Math.max(1,Math.round(sourceH*scale));var ctx=output.getContext('2d');if(!ctx) throw new Error('Canvas is unavailable');ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(roomImage,0,0,output.width,output.height);ctx.save();ctx.fillStyle='rgba(241,232,217,.022)';ctx.fillRect(0,0,output.width,output.height);var ambient=ctx.createLinearGradient(0,0,0,output.height);ambient.addColorStop(0,'rgba(255,255,255,.012)');ambient.addColorStop(.58,'rgba(255,255,255,0)');ambient.addColorStop(1,'rgba(0,0,0,.036)');ctx.fillStyle=ambient;ctx.fillRect(0,0,output.width,output.height);ctx.restore();var artW=output.width*(state.artWidthPercent/100);var artH=artW*(artCanvas.height/artCanvas.width);var x=output.width*(state.centerX/100)-artW/2;var y=output.height*(state.centerY/100)-artH/2;var sampleBoxPadX=Math.max(12,artW*.08);var sampleBoxPadY=Math.max(12,artH*.08);function avgRegion(sx,sy,sw,sh){sx=Math.max(0,Math.round(sx));sy=Math.max(0,Math.round(sy));sw=Math.max(4,Math.round(sw));sh=Math.max(4,Math.round(sh));sw=Math.min(sw,output.width-sx);sh=Math.min(sh,output.height-sy);if(sw<1||sh<1) return {r:225,g:228,b:231,l:228};var sample=document.createElement('canvas');sample.width=24;sample.height=24;var sctx=sample.getContext('2d',{willReadFrequently:true});sctx.drawImage(output,sx,sy,sw,sh,0,0,24,24);var d=sctx.getImageData(0,0,24,24).data;var r=0,g=0,b=0,c=0;for(var i=0;i<d.length;i+=4){if(d[i+3]<10) continue;r+=d[i];g+=d[i+1];b+=d[i+2];c++;}if(!c) return {r:225,g:228,b:231,l:228};r/=c;g/=c;b/=c;return {r:r,g:g,b:b,l:(.2126*r+.7152*g+.0722*b)};}var topAvg=avgRegion(x+artW*.16,Math.max(0,y-sampleBoxPadY),artW*.68,sampleBoxPadY);var leftAvg=avgRegion(Math.max(0,x-sampleBoxPadX),y+artH*.18,sampleBoxPadX,artH*.64);var rightAvg=avgRegion(Math.min(output.width-4,x+artW),y+artH*.18,sampleBoxPadX,artH*.64);var ambientAvg=topAvg||leftAvg||rightAvg;var bright=clamp((ambientAvg.l-124)/255,-.18,.18);var warm=clamp((ambientAvg.r-ambientAvg.b)/255,-.16,.16);var shadowBlur=Math.max(10,artW*.07);var contactBlur=Math.max(4,artW*.024);ctx.save();ctx.shadowColor='rgba(0,0,0,'+(0.16+Math.max(0,.08-bright*.2)).toFixed(3)+')';ctx.shadowBlur=shadowBlur;ctx.shadowOffsetY=Math.max(4,artW*.024);ctx.shadowOffsetX=Math.max(1,artW*.005);ctx.fillStyle='rgba(0,0,0,.001)';ctx.fillRect(x,y,artW,artH);ctx.restore();ctx.save();ctx.shadowColor='rgba(0,0,0,.10)';ctx.shadowBlur=contactBlur;ctx.shadowOffsetY=Math.max(2,artW*.008);ctx.fillStyle='rgba(0,0,0,.001)';ctx.fillRect(x,y,artW,artH);ctx.restore();ctx.save();ctx.filter='brightness('+(0.988+bright*.16).toFixed(3)+') contrast('+(0.992+bright*.04).toFixed(3)+') saturate('+(0.992+warm*.08).toFixed(3)+')';var shear=clamp((state.centerX-50)/50,-1,1)*0.015;ctx.setTransform(1,shear,-shear*.22,1,0,0);ctx.drawImage(artCanvas,x,y-(shear*artW*.04),artW,artH);ctx.setTransform(1,0,0,1,0,0);ctx.restore();ctx.save();var frameWash=ctx.createLinearGradient(x,y,x+artW,y+artH);frameWash.addColorStop(0,'rgba('+Math.round(ambientAvg.r)+','+Math.round(ambientAvg.g)+','+Math.round(ambientAvg.b)+','+(0.022+Math.abs(warm)*.035).toFixed(3)+')');frameWash.addColorStop(.56,'rgba(255,255,255,0)');frameWash.addColorStop(1,'rgba(12,14,18,.022)');ctx.fillStyle=frameWash;ctx.fillRect(x,y,artW,artH);var glaze=ctx.createLinearGradient(x,y,x+artW,y+artH);glaze.addColorStop(0,'rgba(255,255,255,'+(0.065+Math.max(0,bright*.12)).toFixed(3)+')');glaze.addColorStop(.12,'rgba(255,255,255,'+(0.026+Math.max(0,bright*.05)).toFixed(3)+')');glaze.addColorStop(.3,'rgba(255,255,255,0)');glaze.addColorStop(.58,'rgba(255,255,255,.020)');glaze.addColorStop(.77,'rgba(255,255,255,0)');ctx.fillStyle=glaze;ctx.fillRect(x,y,artW,artH);ctx.strokeStyle='rgba(255,255,255,.038)';ctx.lineWidth=Math.max(1,output.width*.001);ctx.strokeRect(x+.5,y+.5,artW-1,artH-1);ctx.beginPath();ctx.strokeStyle='rgba(0,0,0,.09)';ctx.lineWidth=Math.max(1,output.width*.0012);ctx.moveTo(x+artW-.5,y+Math.max(2,artH*.03));ctx.lineTo(x+artW-.5,y+artH-.5);ctx.lineTo(x+Math.max(2,artW*.03),y+artH-.5);ctx.stroke();ctx.restore();try{var grain=document.createElement('canvas');grain.width=Math.max(16,Math.round(artW*.12));grain.height=Math.max(16,Math.round(artH*.12));var gctx=grain.getContext('2d',{willReadFrequently:true});var id=gctx.createImageData(grain.width,grain.height);for(var p=0;p<id.data.length;p+=4){var n=128+Math.round((Math.random()-.5)*18);id.data[p]=n;id.data[p+1]=n;id.data[p+2]=n;id.data[p+3]=10;}gctx.putImageData(id,0,0);ctx.save();ctx.globalAlpha=.08;ctx.globalCompositeOperation='soft-light';ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='medium';ctx.drawImage(grain,x,y,artW,artH);ctx.restore();}catch(error){}if(includeBrandOverlay){if(logoUrl){try{var logo=await loadImage(logoUrl);var maxLogoW=artW*.72;var maxLogoH=artH*.34;var logoScale=Math.min(maxLogoW/logo.naturalWidth,maxLogoH/logo.naturalHeight);var logoW=logo.naturalWidth*logoScale;var logoH=logo.naturalHeight*logoScale;ctx.save();ctx.globalAlpha=.17;ctx.drawImage(logo,x+(artW-logoW)/2,y+(artH-logoH)/2,logoW,logoH);ctx.restore();}catch(error){}}var credit='@sportscaveshop  •  sportscaveshop.com';var creditFont=Math.max(18,Math.min(34,output.width*.018));ctx.save();ctx.font='700 '+creditFont+'px Montserrat, Arial, sans-serif';ctx.textBaseline='middle';var creditWidth=ctx.measureText(credit).width;var padX=creditFont*.8;var padY=creditFont*.52;var creditBoxW=Math.min(output.width*.88,creditWidth+padX*2);var creditBoxH=creditFont+padY*2;var creditX=(output.width-creditBoxW)/2;var creditY=output.height-creditBoxH-Math.max(18,output.height*.035);var radius=Math.min(creditBoxH/2,creditFont*.7);ctx.beginPath();ctx.moveTo(creditX+radius,creditY);ctx.lineTo(creditX+creditBoxW-radius,creditY);ctx.quadraticCurveTo(creditX+creditBoxW,creditY,creditX+creditBoxW,creditY+radius);ctx.lineTo(creditX+creditBoxW,creditY+creditBoxH-radius);ctx.quadraticCurveTo(creditX+creditBoxW,creditY+creditBoxH,creditX+creditBoxW-radius,creditY+creditBoxH);ctx.lineTo(creditX+radius,creditY+creditBoxH);ctx.quadraticCurveTo(creditX,creditY+creditBoxH,creditX,creditY+creditBoxH-radius);ctx.lineTo(creditX,creditY+radius);ctx.quadraticCurveTo(creditX,creditY,creditX+radius,creditY);ctx.closePath();ctx.fillStyle='rgba(11,11,13,.56)';ctx.fill();ctx.strokeStyle='rgba(212,165,76,.38)';ctx.lineWidth=Math.max(1,output.width*.0009);ctx.stroke();ctx.fillStyle='rgba(255,252,247,.94)';ctx.textAlign='center';ctx.shadowColor='rgba(0,0,0,.30)';ctx.shadowBlur=Math.max(1,output.width*.0015);ctx.fillText(credit,output.width/2,creditY+creditBoxH/2+.5);ctx.restore();}return output;}
function canvasToBlob(canvas,type,quality){return new Promise(function(resolve,reject){canvas.toBlob(function(blob){if(blob) resolve(blob);else reject(new Error('Could not create preview image'));},type||'image/jpeg',quality||.94);});}
function previewFilename(){var handle=root.getAttribute('data-product-handle')||'sports-cave';return 'sports-cave-'+handle+'-wall-preview.jpg';}
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

}

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
function createEngagementTracker(){

var visit='',visitor='',source='',opened=false,focused=true,pageActive=true,total=0,anchor=0,lastInput=0,timer=0;

try{visitor=sessionStorage.getItem('sc-wall-analytics-visitor')||makeId();sessionStorage.setItem('sc-wall-analytics-visitor',visitor);}catch(_){visitor=makeId();}

function now(){return performance.now();}

function active(){return opened&&focused&&pageActive&&document.visibilityState==='visible'&&!overlay.hidden;}

function accrue(){var t=now();if(anchor)total+=Math.max(0,Math.min(t,lastInput+60000)-anchor);anchor=active()?t:0;}

function send(name,final){try{

 if(!visit)return;accrue();var variant=currentVariant(),page=new URL(location.href),ref;

 var data={event:name,event_id:makeId(),occurred_at:new Date().toISOString(),session_id:sessionId,

  wall_preview_session_id:visit,visitor_id:visitor,client_preview_id:state.clientPreviewId,

  product_id:String(root.getAttribute('data-product-id')||''),product_handle:String(root.getAttribute('data-product-handle')||''),

  variant_id:variant&&variant.id?String(variant.id):'',device_type:state.isMobileCamera?(Math.min(screen.width,screen.height)>=600?'tablet':'mobile'):'desktop',

  capture_source:source,active_seconds:Math.min(86400,Math.round(total)/1000),page_url:page.origin+page.pathname};

 ['utm_source','utm_medium','utm_campaign','utm_content','utm_term'].forEach(function(k){data[k]=(page.searchParams.get(k)||'').slice(0,160);});

 try{ref=new URL(document.referrer);data.referrer=ref.origin+ref.pathname;}catch(_){}

 var endpoint=String(root.getAttribute('data-wall-inbox-url')||'').replace(/\/$/,'')+'/analytics/events',body=JSON.stringify(data);

 // Same immutable event/body for bounded retries. Beacon is best effort, not a delivery claim.

 if(final&&navigator.sendBeacon&&navigator.sendBeacon(endpoint,new Blob([body],{type:'text/plain'})))return;

 function post(attempt){try{fetch(endpoint,{method:'POST',headers:{'Content-Type':'text/plain'},body:body,credentials:'omit',keepalive:true}).then(function(r){

  if(attempt<2&&(r.status===429||r.status>=500)){var raw=r.headers.get('Retry-After'),seconds=Number(raw),delay=raw?(Number.isFinite(seconds)?seconds*1000:Date.parse(raw)-Date.now()):1000*Math.pow(2,attempt);window.setTimeout(function(){post(attempt+1);},Math.max(1000,delay||1000));}

 }).catch(function(){if(attempt<2)window.setTimeout(function(){post(attempt+1);},1000*Math.pow(2,attempt));});}catch(_){}}

 post(0);

}catch(_){} }

function resume(){accrue();lastInput=now();anchor=active()?now():0;}

listen(document,'visibilitychange',function(){accrue();if(document.visibilityState!=='visible')send('wall_preview_active_time',true);else resume();});

listen(window,'blur',function(){accrue();focused=false;anchor=0;send('wall_preview_active_time',true);});

listen(window,'focus',function(){focused=true;resume();});

listen(window,'pagehide',function(){accrue();pageActive=false;anchor=0;send('wall_preview_active_time',true);});

listen(window,'pageshow',function(){pageActive=true;resume();});

['pointerdown','pointermove','keydown'].forEach(function(type){listen(overlay,type,function(){if(now()-lastInput>1000)resume();});});

return {

 click:function(){if(!opened){visit=makeId();source='';total=0;anchor=0;}send('wall_preview_cta_click');},

 open:function(){if(opened)return;if(!visit)visit=makeId();opened=true;resume();send('wall_preview_open');timer=window.setInterval(function(){if(active())send('wall_preview_active_time');},15000);},

 event:function(name){send(name);},

 source:function(value){source=value;},

 close:function(){if(!opened)return;accrue();opened=false;anchor=0;window.clearInterval(timer);send('wall_preview_close',true);visit='';}

};

}
function fireLocalPreviewEvent(name,detail){var variant=currentVariant();var payload=Object.assign({event:name,preview_id:state.previewId||'',client_preview_id:state.clientPreviewId||'',product_id:String(root.getAttribute('data-product-id')||''),product_handle:String(root.getAttribute('data-product-handle')||''),frame:frameName(state.frame),size:state.sizeInfo?state.sizeInfo.token:'',variant_id:variant&&variant.id?String(variant.id):''},detail||{});try{document.dispatchEvent(new CustomEvent('sports-cave:wall-preview',{detail:payload}));}catch(error){}try{window.dataLayer=window.dataLayer||[];window.dataLayer.push(Object.assign({event:name},payload));}catch(error){}}
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

job.then(function(result){fireLocalPreviewEvent(result.archive_status==='archived'?'wall_preview_saved':'wall_preview_save_queued',{client_preview_id:snapshot.get('client_preview_id'),archive_status:result.archive_status||'accepted',product_id:snapshot.get('product_id'),variant_id:snapshot.get('variant_id'),frame:snapshot.get('frame'),size:snapshot.get('size')});},function(){try{console.warn('[Sports Cave Wall Preview] preview archive unavailable after bounded retries');}catch(error){}});

return job;

}
function cssEscape(value){value=String(value||'');if(window.CSS&&typeof window.CSS.escape==='function') return window.CSS.escape(value);return value.replace(/"/g,'\\"');}
function optionGroup(optionName){var picker=productPickerFor(root);if(!picker) return null;optionName=String(optionName||'').toLowerCase();var groups=picker.querySelectorAll('.option-selector');for(var i=0;i<groups.length;i++){var name=String(groups[i].getAttribute('data-option')||'').toLowerCase();if(name===optionName) return groups[i];}return null;}
function optionValue(group){if(!group) return null;var picker=productPickerFor(root);var checked=group.querySelector('input.js-option:checked')||group.querySelector('input[type="radio"]:checked')||group.querySelector('input.js-option:not([disabled])');if(!checked) return null;var label=checked.id&&picker?picker.querySelector('label[for="'+cssEscape(checked.id)+'"]'):null;var valueNode=label?label.querySelector('.js-value'):null;return String((valueNode?valueNode.textContent:checked.value)||'').trim();}
function selectedOptions(){return PRODUCT_OPTS.map(function(optionName){var name=String(optionName||'').toLowerCase();if(name.indexOf('size')>-1&&state.sizeRaw) return state.sizeRaw;return optionValue(optionGroup(optionName));});}
function variantFromPageForm(){var picker=productPickerFor(root);var scope=picker&&picker.closest?picker.closest('product-info,.product,.product-info,[data-product-id],[id^="shopify-section-"],.shopify-section'):null;var inputs=(scope||document).querySelectorAll('form[action*="/cart/add"] input[name="id"],input[name="id"][data-variant-id]');for(var i=0;i<inputs.length;i+=1){var id=Number(inputs[i].value||inputs[i].getAttribute('data-variant-id')||0);if(!id) continue;var match=VARIANTS.find(function(v){return v&&Number(v.id)===id;});if(match) return match;}return null;}
function currentVariant(){var chosen=selectedOptions();var exact=VARIANTS.find(function(variant){if(!variant||!variant.options) return false;for(var i=0;i<chosen.length;i++){if(chosen[i]&&String(variant.options[i])!==String(chosen[i])) return false;}return true;});if(exact) return exact;var fromForm=variantFromPageForm();if(fromForm) return fromForm;try{var variantParam=Number(new URL(window.location.href).searchParams.get('variant')||0);if(variantParam){var fromUrl=VARIANTS.find(function(v){return v&&Number(v.id)===variantParam;});if(fromUrl) return fromUrl;}}catch(error){}return VARIANTS[0]||null;}
function shareProductUrl(){try{var url=new URL(window.location.href);url.hash='';var variant=currentVariant();if(variant&&variant.id){url.searchParams.set('variant',String(variant.id));}return url.href;}catch(error){return window.location.href;}}
var acceptedPhoto=null,saveStartedForPhoto=0,layoutObserver=null;
var engagement=createEngagementTracker();
function previewIsReady(){return state.photoReady&&!state.artworkFailed&&(state.quickPreview||state.calibrated);}
function setStagePhotoState(){overlay.classList.toggle('is-photo-ready',state.photoReady);}
function syncFromProductPage(skipArtworkDraw){state.frame=currentFrameFromPicker(root);var pageUnit=currentUnitFromPicker(root);if(pageUnit&&!state.photoReady) setUnit(pageUnit);var raw=currentSizeFromPicker(root);var button=raw?findButtonForRaw(raw):null;syncSizeAvailabilityFromPicker();if(button&&!button.disabled) selectSizeButton(button,false,false);else if(!state.sizeInfo) selectSizeButton(getSelectedSizeButton(),false);if(frameLabel) frameLabel.textContent=frameName(state.frame);if(state.photoReady&&!skipArtworkDraw) drawArtwork();updateStatus();}
function setPhotoLandscapeLayout(value){state.photoLandscape=value;}
function syncArtworkEffects(){
 if(!state.photoReady||artCanvas.hidden){artFx.hidden=true;return;}
 var a=artCanvas.getBoundingClientRect(),r=stage.getBoundingClientRect();
 applyLiveArtworkPhotorealism();artFx.hidden=state.frame==='unframed';
 artFx.style.cssText='left:'+(a.left-r.left)+'px;top:'+(a.top-r.top)+'px;width:'+a.width+'px;height:'+a.height+'px';
}
function fitPreview(){
 if(!state.photoReady||!roomImage.naturalWidth)return;
 var ratio=roomImage.naturalWidth/roomImage.naturalHeight;
 var maxH=Math.max(130,Math.min(innerHeight*.58,innerHeight-190));
 stage.style.width=Math.min(modal.clientWidth-32,maxH*ratio)+'px';
 stage.style.aspectRatio=String(ratio);positionMeasurementVisuals();if(state.calibrated)applyScaledSize();else if(state.quickPreview)applyQuickPreviewSize();requestArtworkEffectsSync();
}
function autoPlacePhoto(sequence){
 if(sequence!==photoLoadSeq||overlay.hidden||!state.photoReady)return;
 syncFromProductPage(true);state.quickPreview=false;initialScalePrompt=false;
 state.centerX=50;state.centerY=44;applyArtworkPosition();fitPreview();
 startPointSelection();
 // Prepare the existing renderer in the background; never reveal art before measurement.
 return drawArtwork().then(function(){
  if(sequence!==photoLoadSeq||overlay.hidden)return;
  renderScaleHelp();updateStickyBuy();setPreviewActionState();
 });
}
function savePlacedPhoto(sequence){
 if(sequence!==photoLoadSeq||overlay.hidden||(!state.calibrated&&!state.quickPreview)||state.artworkFailed||artCanvas.hidden||saveStartedForPhoto===sequence)return;
 state.confirmed=true;saveStartedForPhoto=sequence;
 var metadata=archiveMetadata();
 fireLocalPreviewEvent('wall_preview_placed');engagement.event('wall_preview_placement_confirmed');
 queuePreviewSave(ensureSavedPreviewAsset(true),null,undefined,metadata).catch(function(){});
}
function activatePhoto(file,fromCameraTransition,desktopFallbackTried){
 if(!isImageUploadFile(file)||overlay.hidden||acceptedPhoto===file)return;
 acceptedPhoto=file;stopLiveCamera();cameraCaptureSeq+=1;
 var sequence=++photoLoadSeq;
 if(objectUrl)URL.revokeObjectURL(objectUrl);
 objectUrl=URL.createObjectURL(file);savedBlob=null;assetPromise=null;assetRevision+=1;
 state.confirmed=false;state.photoReady=false;state.quickPreview=false;state.calibrated=false;state.calibrationActive=false;state.awaitingMeasurement=false;state.pointA=null;state.pointB=null;state.referenceMeasurement=0;initialScalePrompt=true;
 state.storageSaved=false;state.storageAccepted=false;state.clientPreviewId=makeId();
 state.startedAt=new Date().toISOString();artCanvas.hidden=true;artFx.hidden=true;
 roomImage.onload=function(){
  if(sequence!==photoLoadSeq||overlay.hidden)return;
  roomImage.onerror=null;clearCaptureFreeze();roomImage.style.visibility='';
  captureTransitionPending=false;state.photoReady=true;
  intro.hidden=true;editor.hidden=false;setStagePhotoState();
  engagement.source(fromCameraTransition?'camera':'upload');engagement.event('wall_preview_photo_loaded');
  autoPlacePhoto(sequence);
 };
 roomImage.onerror=function(){
  if(sequence!==photoLoadSeq||overlay.hidden)return;
  if(!desktopFallbackTried&&!state.isMobileCamera){
   normalizeDesktopUploadFallback(file).then(function(normalized){
    if(sequence!==photoLoadSeq||overlay.hidden)return;
    acceptedPhoto=null;activatePhoto(normalized,fromCameraTransition,true);
   }).catch(function(){if(sequence===photoLoadSeq)photoFailure();});
  }else photoFailure();
 };
 roomImage.src=objectUrl;
}
function photoFailure(){returnToPhotoStart();deviceNote.textContent='Could not open that photo. Please choose another.';deviceNote.hidden=false;}
function showCaptureFreeze(canvas){
 clearCaptureFreeze();captureTransitionPending=true;captureFreezeCanvas=canvas;
 canvas.className='sc-wall-v1__room';canvas.setAttribute('aria-hidden','true');
 stage.insertBefore(canvas,stage.firstChild);stage.style.aspectRatio=String(canvas.width/canvas.height);
 stage.style.width=Math.min(modal.clientWidth-32,innerHeight*.58*canvas.width/canvas.height)+'px';
 roomImage.style.visibility='hidden';intro.hidden=true;editor.hidden=false;liveCamera.hidden=true;
}
function returnToPhotoStart(){
 calibrationSnapshot=null;
 photoLoadSeq+=1;artworkRenderRevision+=1;cameraCaptureSeq+=1;stopLiveCamera();clearCaptureFreeze();
 roomImage.onload=null;roomImage.onerror=null;roomImage.removeAttribute('src');roomImage.style.visibility='';
 if(objectUrl){URL.revokeObjectURL(objectUrl);objectUrl='';}
 acceptedPhoto=null;captureTransitionPending=false;state.photoReady=false;state.confirmed=false;state.quickPreview=false;state.calibrated=false;state.calibrationActive=false;state.awaitingMeasurement=false;
 savedBlob=null;savedFile=null;assetPromise=null;assetRevision+=1;
 artCanvas.hidden=true;artFx.hidden=true;artError.hidden=true;editor.hidden=true;intro.hidden=false;
 deviceNote.hidden=true;setStagePhotoState();closeDownloadGate();updateStickyBuy();setPreviewActionState();
}
function mountOverlayToBody(){if(overlay.parentNode!==document.body)document.body.appendChild(overlay);}
function restoreOverlayHome(){if(overlayHomeParent?.isConnected)overlayHomeParent.appendChild(overlay);}
function showDialog(){
 if(!overlay.hidden)return;
 dialogSession+=1;lastMainCloseAt=0;lastPreviewToolTouchAt=0;lastActiveElement=document.activeElement;rememberPagePosition();syncFromProductPage();
 state.isMobileCamera=isMobileCameraDevice();
 savedBodyOverflow=document.body.style.overflow;savedHtmlOverflow=document.documentElement.style.overflow;
 mountOverlayToBody();document.body.style.overflow='hidden';document.documentElement.style.overflow='hidden';
 overlay.hidden=false;overlay.setAttribute('aria-hidden','false');
 document.querySelectorAll('[data-sc-wall-launch]').forEach(function(b){b.setAttribute('aria-expanded','true');});
 engagement.click();fireLocalPreviewEvent('WallPreviewStarted');engagement.open();
 closeButton.focus({preventScroll:true});
}
function closeDialog(){
 if(overlay.hidden)return;
 dialogSession+=1;engagement.close();overlay.hidden=true;overlay.setAttribute('aria-hidden','true');overlay.style.removeProperty('z-index');
 // Published-theme cleanup, adapted only for the external launcher/lightweight shell.
 document.body.style.overflow=savedBodyOverflow;document.documentElement.style.overflow=savedHtmlOverflow;
 try{closeSharePopup();}catch(error){}try{closeDownloadGate();}catch(error){}try{returnToPhotoStart();}catch(error){}
 if(cameraInput)cameraInput.value='';if(uploadInput)uploadInput.value='';
 stage.style.aspectRatio='';stage.classList.remove('is-calibrating','is-measuring');stickyBuy.hidden=true;
 document.querySelectorAll('[data-sc-wall-launch],[data-sc-wall-preview-trigger]').forEach(function(button){button.setAttribute('aria-expanded','false');});
 restoreOverlayHome();restorePagePosition();window.setTimeout(clearCartLayerIfClosed,0);
 if(lastActiveElement?.isConnected&&!document.body.classList.contains('sc-wall-cart-layer')){try{lastActiveElement.focus({preventScroll:true});}catch(error){}}
 lastActiveElement=null;
}
function setUnit(unit){unit=unit==='in'?'in':'cm';state.unit=unit;root.setAttribute('data-unit',unit);var unitSelect=overlay.querySelector('[data-sc-wall-unit-select]');if(unitSelect)unitSelect.value=unit;if(measurementUnit) measurementUnit.textContent=unit;if(scaleUnitInline) scaleUnitInline.textContent=unit;if(referenceMeasurement) referenceMeasurement.placeholder='';renderSizeButtons();updateStatus();renderScaleHelp();if(state.calibrated&&!state.quickPreview) applyScaledSize();}
function getSelectedSizeButton(){return sizeButtons.find(function(btn){return btn.getAttribute('aria-pressed')==='true';})||sizeButtons.find(function(btn){return !btn.disabled;})||sizeButtons[0]||null;}
function findButtonForRaw(raw){raw=clean(raw);var exact=sizeButtons.find(function(btn){return clean(btn.getAttribute('data-size-raw')||'')===raw;});if(exact) return exact;var parsed=parseSizeInfo(raw,0);return sizeButtons.find(function(btn){var info=btn.__scSizeInfo||parseSizeInfo(btn.getAttribute('data-size-raw')||'',Number(btn.getAttribute('data-size-index')||0));return info.token===parsed.token;})||null;}
function sizeGroupFromPicker(){var picker=productPickerFor(root);if(!picker) return null;var group=null;picker.querySelectorAll('.option-selector').forEach(function(item){var name=String(item.getAttribute('data-option')||'').toLowerCase();if(!group&&name.indexOf('size')>-1) group=item;});return group;}
function syncSizeToPicker(raw,token){var group=sizeGroupFromPicker();if(!group) return;var input=Array.prototype.find.call(group.querySelectorAll('input[type="radio"]'),function(item){return clean(item.value)===clean(raw);});if(!input&&token){input=Array.prototype.find.call(group.querySelectorAll('input[type="radio"]'),function(item){return parseSizeInfo(item.value,0).token===token;});}if(!input||input.checked) return;input.checked=true;input.dispatchEvent(new Event('change',{bubbles:true}));}
function updateStatus(){if(frameLabel) frameLabel.textContent=frameName(state.frame);if(sizeSummary) sizeSummary.textContent=state.sizeInfo?state.sizeInfo.token+' • '+formatSize(state.sizeInfo,state.unit):'';}
function calibrationDistancePx(){if(!state.pointA||!state.pointB) return 0;var rect=stage.getBoundingClientRect();if(!rect.width||!rect.height) return 0;var dx=((state.pointB.x-state.pointA.x)/100)*rect.width;var dy=((state.pointB.y-state.pointA.y)/100)*rect.height;return Math.sqrt(dx*dx+dy*dy);}
function positionMeasurementVisuals(){if(!state.calibrationActive&&!state.awaitingMeasurement){if(pointAEl) pointAEl.hidden=true;if(pointBEl) pointBEl.hidden=true;if(measureLine) measureLine.hidden=true;return;}if(state.pointA&&pointAEl){pointAEl.hidden=false;pointAEl.style.left=state.pointA.x+'%';pointAEl.style.top=state.pointA.y+'%';}else if(pointAEl){pointAEl.hidden=true;}if(state.pointB&&pointBEl){pointBEl.hidden=false;pointBEl.style.left=state.pointB.x+'%';pointBEl.style.top=state.pointB.y+'%';}else if(pointBEl){pointBEl.hidden=true;}if(!measureLine||!state.pointA||!state.pointB){if(measureLine) measureLine.hidden=true;return;}var rect=stage.getBoundingClientRect();var x1=state.pointA.x/100*rect.width;var y1=state.pointA.y/100*rect.height;var x2=state.pointB.x/100*rect.width;var y2=state.pointB.y/100*rect.height;var dx=x2-x1,dy=y2-y1;var distance=Math.sqrt(dx*dx+dy*dy);var angle=Math.atan2(dy,dx)*180/Math.PI;measureLine.hidden=false;measureLine.style.left=state.pointA.x+'%';measureLine.style.top=state.pointA.y+'%';measureLine.style.width=distance+'px';measureLine.style.transform='translateY(-50%) rotate('+angle+'deg)';}
function showMeasurementStep(){var distance=calibrationDistancePx();if(distance<12){state.pointA=null;state.pointB=null;positionMeasurementVisuals();if(state.scaleHelpDismissed&&tapInstruction){tapInstruction.textContent='Try again — tap one end';tapInstruction.hidden=false;}renderScaleHelp();return;}state.calibrationActive=false;state.awaitingMeasurement=true;state.scaleHelpDismissed=false;stage.classList.remove('is-calibrating');positionMeasurementVisuals();if(tapInstruction) tapInstruction.hidden=true;renderScaleHelp();if(referenceMeasurement){referenceMeasurement.value='';window.requestAnimationFrame(function(){window.setTimeout(function(){try{referenceMeasurement.focus({preventScroll:true});}catch(error){try{referenceMeasurement.focus();}catch(innerError){}}window.setTimeout(function(){if(root.__scPositionMeasurementEntry)root.__scPositionMeasurementEntry();},120);},90);});}}
function submitMeasurement(){var raw=referenceMeasurement?String(referenceMeasurement.value||'').trim().replace(',','.').replace(/[^0-9.]/g,''):'';var amount=Number(raw);if(!Number.isFinite(amount)||amount<=0){setFlowError('Enter the distance between your two points.');if(referenceMeasurement){try{referenceMeasurement.focus({preventScroll:true});referenceMeasurement.select();}catch(error){referenceMeasurement.focus();}}return;}if(referenceMeasurement) referenceMeasurement.value=String(raw);setFlowError('');calibrationSnapshot=null;initialScalePrompt=false;state.referenceMeasurement=amount;state.awaitingMeasurement=false;state.quickPreview=false;state.hasDraggedPlacement=false;state.calibrated=true;hideScaleHelp();positionMeasurementVisuals();var measurementPhoto=photoLoadSeq;drawArtwork().then(function(){if(measurementPhoto!==photoLoadSeq||overlay.hidden)return;applyScaledSize();savePlacedPhoto(measurementPhoto);window.requestAnimationFrame(fitPreview);});}
function quickPreviewLargestWidth(){var largest=0;sizeButtons.forEach(function(button,index){if(button.disabled) return;var info=button.__scSizeInfo||parseSizeInfo(button.getAttribute('data-size-raw')||'',Number(button.getAttribute('data-size-index')||index));if(info&&Number.isFinite(info.widthCm)) largest=Math.max(largest,info.widthCm);});return largest||87;}
function stageCalibrationTap(event){if(!state.calibrationActive) return;if(event.button!==undefined&&event.button!==0) return;event.preventDefault();var rect=stage.getBoundingClientRect();if(!rect.width||!rect.height) return;var point={x:clamp((event.clientX-rect.left)/rect.width*100,0,100),y:clamp((event.clientY-rect.top)/rect.height*100,0,100)};if(!state.pointA){state.pointA=point;positionMeasurementVisuals();if(state.scaleHelpDismissed&&tapInstruction){tapInstruction.textContent='Tap the other end';tapInstruction.hidden=false;}renderScaleHelp();}else{state.pointB=point;positionMeasurementVisuals();showMeasurementStep();}}
function moveDrag(event){if(!state.dragging||event.pointerId!==state.dragPointerId) return;event.preventDefault();var rect=stage.getBoundingClientRect();if(!rect.width||!rect.height) return;var dx=event.clientX-state.dragStartX,dy=event.clientY-state.dragStartY;if(Math.sqrt(dx*dx+dy*dy)>=4) state.hasDraggedPlacement=true;state.centerX=clamp(state.dragStartCenterX+dx/rect.width*100,-100,200);state.centerY=clamp(state.dragStartCenterY+dy/rect.height*100,-100,200);applyArtworkPosition();}
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
function elevateCartDrawer(){var drawer=cartDrawer();if(!drawer) return false;document.body.classList.add('sc-wall-cart-layer');if(overlay) overlay.style.setProperty('z-index','2147483600','important');var section=drawer.closest('[id^="shopify-section-"],.shopify-section');if(section){section.style.setProperty('position','relative','important');section.style.setProperty('z-index','2147483646','important');}drawer.style.setProperty('z-index','2147483647','important');var backdrop=document.querySelector('[data-sc-cart-backdrop],.sc-cart-backdrop,[data-drawer-overlay]');if(backdrop){backdrop.style.setProperty('z-index','2147483645','important');if(drawer.getAttribute('aria-hidden')==='false'||drawer.classList.contains('is-open')){backdrop.classList.remove('hidden');backdrop.setAttribute('aria-hidden','false');}}return true;}
function verifyCartDrawerLayer(){if(!overlay||overlay.hidden) return;var drawer=cartDrawer();if(!drawer) return;var rect=drawer.getBoundingClientRect();if(rect.width<20||rect.height<20) return;var x=Math.max(2,Math.min(window.innerWidth-2,rect.left+Math.min(rect.width*.5,Math.max(12,rect.width-12))));var y=Math.max(2,Math.min(window.innerHeight-2,rect.top+Math.min(72,Math.max(12,rect.height-12))));var topEl=document.elementFromPoint(x,y);if(topEl&&(topEl===drawer||drawer.contains(topEl))) return;closeDialog();}
function openCartDrawer(){elevateCartDrawer();try{document.dispatchEvent(new CustomEvent('dispatch:cart-drawer:open',{bubbles:true,detail:{source:'sports-cave-wall-visualizer'}}));document.dispatchEvent(new CustomEvent('cart:open',{bubbles:true,detail:{source:'sports-cave-wall-visualizer'}}));}catch(error){}var drawer=cartDrawer();if(!drawer){closeDialog();return;}elevateCartDrawer();try{if(typeof drawer.open==='function') drawer.open();drawer.setAttribute('open','');drawer.setAttribute('aria-hidden','false');drawer.removeAttribute('inert');drawer.classList.add('is-open','active','open');document.body.classList.add('drawer-open','cart-drawer-open');}catch(error){}window.setTimeout(function(){elevateCartDrawer();verifyCartDrawerLayer();},450);}
async function renderCart(ids,addJson){if(addJson&&addJson.sections){applySections(addJson.sections);}else if(ids.length){try{var response=await fetch(route('?sections='+encodeURIComponent(ids.join(','))),{headers:{'Accept':'application/json'},credentials:'same-origin'});if(response.ok) applySections(await response.json());}catch(error){}}var cart=null;try{cart=await fetchCart();}catch(error){}var count=cart&&typeof cart.item_count==='number'?cart.item_count:1;updateCartBubble(count);markDrawerFilled(count);dispatchCartEvents(cart);return cart;}
function editionArchived(){return root.getAttribute('data-edition-expired')==='1';}
function setCartLoading(loading){
if(!stickySecure) return;
cartBusy=!!loading;stickySecure.classList.toggle('is-loading',!!loading);
if(loading){
stickySecure.disabled=true;
cartAddedUntil=0;stickySecure.classList.remove('is-added');stickySecure.setAttribute('aria-busy','true');
setStickyCartState();return;
}
stickySecure.removeAttribute('aria-busy');
setStickyCartState();
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
if(!stickySecure||cartBusy||stickySecure.disabled||editionArchived()) return;
var variant=selectedVariantForCart();
if(!variant||!variant.id||variant.available===false){
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
cartAddedUntil=Date.now()+1300;stickySecure.classList.remove('is-loading');stickySecure.classList.add('is-added');setStickyCartState();
window.clearTimeout(cartSuccessTimer);cartSuccessTimer=window.setTimeout(function(){cartAddedUntil=0;stickySecure.classList.remove('is-added');setStickyCartState();},1300);
engagement.event('wall_preview_add_to_cart');if(state.previewId) emitPreviewEvent('WallPreviewAddedToCart');
await renderCart(ids,json);
window.setTimeout(openCartDrawer,60);
}catch(error){
if(stickyCartError){stickyCartError.textContent=(error&&error.message)?error.message:'Could not add this edition. Please try again.';stickyCartError.classList.add('is-visible');}
}finally{
setCartLoading(false);
}
}
function rememberDownloadIdentity(identity){if(!identity||identity.source==='logged_in') return;try{window.sessionStorage.setItem(DOWNLOAD_IDENTITY_KEY,JSON.stringify({email:identity.email,name:identity.name}));}catch(error){}}
function setDownloadError(value){if(downloadError) downloadError.textContent=value||'';}
function openDownloadGate(){if(!downloadGate||!state.confirmed) return;var identity=loggedInIdentity()||sessionDownloadIdentity();if(downloadName) downloadName.value=identity&&identity.name?identity.name:'';if(downloadEmail) downloadEmail.value=identity&&identity.email?identity.email:'';if(downloadConsent) downloadConsent.checked=true;setDownloadError('');downloadGate.hidden=false;downloadGate.setAttribute('aria-hidden','false');setPreviewActionState();window.setTimeout(function(){var target=(downloadName&&!downloadName.value)?downloadName:downloadEmail;if(target&&!overlay.hidden&&!downloadGate.hidden){try{target.focus();}catch(error){}}},30);}
function closeDownloadGate(){if(!downloadGate) return;downloadGate.setAttribute('aria-hidden','true');downloadGate.hidden=true;setDownloadError('');if(downloadConfirm){downloadConfirm.disabled=false;downloadConfirm.textContent='Download Preview';}setPreviewActionState();}
function downloadIdentityFromGate(){var name=clean(downloadName?downloadName.value:'');var email=String(downloadEmail?downloadEmail.value:'').trim().toLowerCase();if(name.length<2){setDownloadError('Enter your name.');if(downloadName) downloadName.focus();return null;}if(!validIdentityEmail(email)){setDownloadError('Enter a valid email address.');if(downloadEmail) downloadEmail.focus();return null;}var logged=loggedInIdentity();return {email:email,name:name,shopifyCustomerId:logged&&logged.shopifyCustomerId?logged.shopifyCustomerId:'',source:logged&&logged.email===email?'logged_in':'guest'};}
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
var downloadSession=dialogSession;
var ready=await ensureSavedPreviewAsset();
if(downloadSession!==dialogSession||overlay.hidden)return;
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
if(state.clientPreviewId!==downloadCapture||downloadSession!==dialogSession||overlay.hidden) return;
setShareNote(archive&&archive.archive_status==='archived'?'Downloaded — Sports Cave copy saved.':'Downloaded to your device.');
},function(){if(state.clientPreviewId===downloadCapture&&downloadSession===dialogSession&&!overlay.hidden) setShareNote('Downloaded to your device.');});
}catch(error){
if(downloadSession!==dialogSession||overlay.hidden)return;
if(savedBlob){
setShareNote('Downloaded to your device.');
try{console.warn('[Sports Cave Wall Preview] customer archive pending',error);}catch(logError){}
}else{
setDownloadError('Could not prepare this preview. Please try again.');
if(downloadGate){downloadGate.hidden=false;downloadGate.setAttribute('aria-hidden','false');}
}
}finally{
if(downloadSession!==dialogSession||overlay.hidden)return;
if(downloadConfirm){downloadConfirm.disabled=false;downloadConfirm.textContent='Download Preview';}
window.setTimeout(function(){if(downloadSession!==dialogSession||overlay.hidden)return;if(saveLabel&&state.confirmed) saveLabel.textContent='Download Your Preview';if(saveButton&&state.confirmed){saveButton.setAttribute('aria-label','Download your wall preview');saveButton.setAttribute('title','Download preview');}},1600);
}
}
function downloadBlob(blob){var url=URL.createObjectURL(blob);var link=document.createElement('a');link.href=url;link.download=previewFilename();document.body.appendChild(link);link.click();link.remove();window.setTimeout(function(){URL.revokeObjectURL(url);},1800);}
function canNativeShareFile(file){try{return !!(navigator.share&&navigator.canShare&&navigator.canShare({files:[file]}));}catch(error){return false;}}
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
var shareSession=dialogSession;
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
if(shareSession!==dialogSession||overlay.hidden)return;
emitPreviewEvent('WallPreviewShared');
setSharePreviewLabel('Shared ✓');
}).catch(function(error){
if(shareSession!==dialogSession||overlay.hidden)return;
if(error&&error.name==='AbortError'){setSharePreviewLabel('Share Preview');}
else{copyShareText(shareText);setSharePreviewLabel('Link Copied ✓');}
}).finally(function(){
window.setTimeout(function(){
if(shareSession===dialogSession&&!overlay.hidden&&state.photoReady&&previewIsReady()&&!artCanvas.hidden){sharePreviewButton.disabled=false;setSharePreviewLabel('Share Preview');}
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
function emitPreviewEvent(name,extra){fireLocalPreviewEvent(name,extra);var aliases={WallPreviewDownloaded:'wall_preview_downloaded',WallPreviewShared:'wall_preview_shared',WallPreviewAddedToCart:'wall_preview_add_to_cart'};if(aliases[name]) fireLocalPreviewEvent(aliases[name],extra);if(!state.previewId||['WallPreviewDownloaded','WallPreviewShared','WallPreviewAddedToCart'].indexOf(name)<0) return;var endpoint=String(root.getAttribute('data-wall-inbox-url')||'').trim();if(!endpoint) return;try{fetch(endpoint+'/'+encodeURIComponent(state.previewId)+'/events',{method:'POST',headers:{'Accept':'application/json','Content-Type':'application/json','X-Wall-Preview-Token':sessionId},body:JSON.stringify({event_name:name,event_id:makeId(),occurred_at:new Date().toISOString()}),mode:'cors',credentials:'omit',keepalive:true}).catch(function(){});}catch(error){}}
function applyScaledSize(){if(!state.calibrated||!state.sizeInfo||!state.referenceMeasurement) return;var rect=stage.getBoundingClientRect();var refPx=calibrationDistancePx();if(!rect.width||!refPx) return;var artWidth=state.unit==='in'?state.sizeInfo.widthIn:state.sizeInfo.widthCm;var artPx=artWidth*(refPx/state.referenceMeasurement);state.artWidthPercent=clamp((artPx/rect.width)*100,3,500);artCanvas.style.width=state.artWidthPercent.toFixed(3)+'%';artCanvas.hidden=!!state.artworkFailed;setPreviewActionState();renderScaleHelp();requestArtworkEffectsSync();updateStickyBuy();window.setTimeout(primePreviewActionAsset,30);}
function applyQuickPreviewSize(){if(!state.quickPreview||!state.sizeInfo) return;var largest=quickPreviewLargestWidth();var ratio=largest>0?state.sizeInfo.widthCm/largest:1;var quickBase=82,quickMin=22;if(state.photoLandscape){var photoRatio=roomImage.naturalWidth&&roomImage.naturalHeight?roomImage.naturalWidth/roomImage.naturalHeight:1.7778;var artRatio=artCanvas.width&&artCanvas.height?artCanvas.width/artCanvas.height:1.344;var heightSafeBase=(78*artRatio)/Math.max(1.05,photoRatio);quickBase=clamp(Math.min(62,heightSafeBase),34,62);quickMin=15;}state.artWidthPercent=clamp(quickBase*ratio,quickMin,quickBase);artCanvas.style.width=state.artWidthPercent.toFixed(2)+'%';artCanvas.hidden=!!state.artworkFailed;setPreviewActionState();renderScaleHelp();requestArtworkEffectsSync();updateStickyBuy();window.setTimeout(primePreviewActionAsset,30);}
function beginDrag(event){if(!state.photoReady||!previewIsReady()||state.calibrationActive||artCanvas.hidden)return;event.preventDefault();savedBlob=null;assetRevision+=1;assetPromise=null;savedFile=null;state.dragging=true;state.dragPointerId=event.pointerId;state.dragStartX=event.clientX;state.dragStartY=event.clientY;state.dragStartCenterX=state.centerX;state.dragStartCenterY=state.centerY;artCanvas.classList.add('is-dragging');if(artCanvas.setPointerCapture){try{artCanvas.setPointerCapture(event.pointerId);}catch(error){}}}
function endDrag(event){if(!state.dragging) return;if(event&&state.dragPointerId!==null&&event.pointerId!==state.dragPointerId) return;state.dragging=false;artCanvas.classList.remove('is-dragging');if(event&&artCanvas.releasePointerCapture){try{artCanvas.releasePointerCapture(event.pointerId);}catch(error){}}state.dragPointerId=null;if(state.hasDraggedPlacement){window.setTimeout(primePreviewActionAsset,60);}}
// Compact presentation around the original calibration, variant and cart functions.
function invalidateComposite(){savedBlob=null;savedFile=null;assetRevision+=1;assetPromise=null;}
function renderSizeButtons(){sizeButtons.forEach(function(button,index){var info=parseSizeInfo(button.getAttribute('data-size-raw')||'',index);button.__scSizeInfo=info;var raw=button.getAttribute('data-size-raw')||'',label=raw.replace(/\s*[-��]\s*\d[\s\S]*$/,'').trim();button.querySelector('span').textContent=label||raw;button.setAttribute('aria-label',raw);button.title=raw;var dims=button.querySelector('[data-sc-wall-size-dims]');if(dims)dims.textContent=formatSize(info,state.unit);});}
function selectSizeButton(button,syncPicker){
 if(!button||button.disabled)return;
 var next=clean(button.getAttribute('data-size-raw')||'');
 if(next!==state.sizeRaw)invalidateComposite();
 state.sizeRaw=next;state.sizeInfo=button.__scSizeInfo||parseSizeInfo(next,0);
 sizeButtons.forEach(function(b){b.setAttribute('aria-pressed',b===button?'true':'false');});
 if(syncPicker)syncSizeToPicker(state.sizeRaw,state.sizeInfo.token);
 if(state.calibrated)applyScaledSize();else if(state.quickPreview)applyQuickPreviewSize();
 setStickyCartState();
}
function syncSizeAvailabilityFromPicker(){
 var selected=selectedOptions(),sizeIndex=PRODUCT_OPTS.findIndex(function(o){return /size/i.test(o);});
 sizeButtons.forEach(function(button){var value=button.getAttribute('data-size-raw');button.disabled=editionArchived()||!VARIANTS.some(function(v){return v.available&&v.options.every(function(o,i){return i===sizeIndex?o===value:!selected[i]||o===selected[i];});});});
}
function setStickyCartState(){
 if(!stickySecure)return;var variant=currentVariant(),archived=editionArchived();var unavailable=archived||!variant||!variant.available||!previewIsReady()||artCanvas.hidden;
 var added=Date.now()<cartAddedUntil;stickySecure.disabled=unavailable||cartBusy||added;stickySecure.setAttribute('aria-disabled',String(stickySecure.disabled));
 stickyCartLabel.textContent=added?'✓ ADDED':cartBusy?'ADDING...':archived?'Edition Archived':(!variant||!variant.available?'Unavailable':'Add To Cart');
 var fmt=variant?(FORMATTED[String(variant.id)]||{}):{};stickyCartPrice.textContent=!archived&&fmt.price?' · '+fmt.price:'';stickyCartPrice.hidden=cartBusy||added;
}
function updateStickyBuy(){stickyBuy.hidden=!state.photoReady||(!state.calibrated&&!state.quickPreview)||state.calibrationActive||state.awaitingMeasurement;setStickyCartState();}
function setPreviewActionState(){var ready=previewIsReady()&&!artCanvas.hidden&&!state.calibrationActive&&!state.awaitingMeasurement&&downloadGate.hidden;saveWrap.hidden=!state.photoReady||(!state.calibrated&&!state.quickPreview);saveButton.disabled=!ready;sharePreviewButton.disabled=!ready;}
function setShareNote(text){shareNote.textContent=text||'';}
function setFlowError(text){flowError.textContent=text||'';}
function renderScaleHelp(){
 if(!state.photoReady)return;
 var measuring=state.calibrationActive||state.awaitingMeasurement;
 scaleStatus.textContent=state.calibrated?'✓ TRUE SCALE':state.quickPreview?'NOT TO SCALE':state.awaitingMeasurement?'What is that distance?':'Measure something you know';
 scaleCopy.textContent=state.awaitingMeasurement?'Enter the real width in '+(state.unit==='in'?'inches':'cm')+'.':state.pointA?'Tap the other side.':'Tap both sides of an object in your photo that you know the width of — for example a TV, lounge, desk, door or picture frame. Tap the first side.';
 scaleCopy.hidden=!measuring;scaleEntry.hidden=!state.awaitingMeasurement;
 scaleStart.hidden=(!state.calibrated&&!state.quickPreview)||measuring;scaleStart.textContent=state.calibrated?'Reset true scale':'Set true scale';
 skipScale.hidden=!measuring;
 stage.classList.toggle('is-calibrating',state.calibrationActive);stage.classList.toggle('is-measuring',measuring);
 tapDemo.hidden=!(state.calibrationActive&&!state.pointA&&!state.awaitingMeasurement);
 scaleCancel.hidden=!measuring||!(calibrationSnapshot?.state.calibrated||calibrationSnapshot?.state.quickPreview);
 if(measuring){artCanvas.hidden=true;artFx.hidden=true;}
 setPreviewActionState();
}
function hideScaleHelp(){scaleEntry.hidden=true;setFlowError('');renderScaleHelp();}
// Keep the previous preview intact if measurement is cancelled.
function cancelPointSelection(){
 if(!calibrationSnapshot)return;
 Object.assign(state,calibrationSnapshot.state);initialScalePrompt=calibrationSnapshot.initialScalePrompt;calibrationSnapshot=null;
 state.calibrationActive=false;state.awaitingMeasurement=false;setFlowError('');
 invalidateComposite();positionMeasurementVisuals();renderScaleHelp();
 setUnit(state.unit);if(state.calibrated)applyScaledSize();else if(state.quickPreview)applyQuickPreviewSize();
 applyArtworkPosition();requestArtworkEffectsSync();updateStickyBuy();
}
function startPointSelection(){
 if(state.calibrationActive||state.awaitingMeasurement)return;
 calibrationSnapshot={initialScalePrompt:initialScalePrompt,state:{calibrated:state.calibrated,quickPreview:state.quickPreview,referenceMeasurement:state.referenceMeasurement,pointA:state.pointA,pointB:state.pointB,unit:state.unit,scaleHelpDismissed:state.scaleHelpDismissed}};
 artCanvas.hidden=true;artFx.hidden=true;

 invalidateComposite();state.calibrated=false;state.quickPreview=false;state.calibrationActive=true;state.awaitingMeasurement=false;state.referenceMeasurement=0;state.pointA=null;state.pointB=null;state.scaleHelpDismissed=false;
 stage.classList.add('is-calibrating');positionMeasurementVisuals();renderScaleHelp();setPreviewActionState();updateStickyBuy();requestArtworkEffectsSync();
}

// Reuse the existing live quick-preview renderer and physical-size proportions.
function skipTrueScale(){
 if(!state.photoReady||overlay.hidden)return;
 var sequence=photoLoadSeq;calibrationSnapshot=null;invalidateComposite();
 state.calibrated=false;state.quickPreview=true;state.calibrationActive=false;state.awaitingMeasurement=false;
 state.referenceMeasurement=0;state.pointA=null;state.pointB=null;setFlowError('');
 positionMeasurementVisuals();renderScaleHelp();
 drawArtwork().then(function(){
  if(sequence!==photoLoadSeq||overlay.hidden||!state.quickPreview)return;
  applyQuickPreviewSize();applyArtworkPosition();requestArtworkEffectsSync();savePlacedPhoto(sequence);updateStickyBuy();
 });
}
function primePreviewActionAsset(){if(!savedBlob&&previewIsReady()&&!artCanvas.hidden)ensureSavedPreviewAsset();}
function ensurePreviewActionPlacement(){if(!previewIsReady()||artCanvas.hidden)return false;state.confirmed=true;return true;}

root.scWallOpen=showDialog;
root.scWallDestroy=function(){window.clearTimeout(cartSuccessTimer);closeDialog();stopLiveCamera();detach.forEach(function(fn){fn();});layoutObserver?.disconnect();delete root.scWallOpen;};
var lastMainCloseAt=0;
function handleDelegatedMainClose(event){
var target=event.target&&event.target.closest?event.target.closest('[data-sc-wall-close],[data-sc-wall-intro-close]'):null;
if(!target||overlay.hidden||!overlay.contains(target)) return;
if(event.type==='click'&&Date.now()-lastMainCloseAt<700){event.preventDefault();event.stopPropagation();return;}
lastMainCloseAt=Date.now();
event.preventDefault();
event.stopPropagation();
if(event.stopImmediatePropagation) event.stopImmediatePropagation();
closeDialog();
}
// Close on touchend/click, not pointerup: consume the gesture before unmounting.
listen(window,'touchend',handleDelegatedMainClose,{capture:true,passive:false});
listen(window,'click',handleDelegatedMainClose,true);
listen(keepBrowsing,'click',closeDialog);
listen(cameraButton,'click',function(){if(!cameraStream&&!cameraCaptureBusy)startRearCamera();});
listen(uploadButton,'click',chooseUpload);listen(cameraLibrary,'click',chooseUploadFromCamera);
listen(cameraCapture,'click',captureRearCamera);

listen(artRetry,'click',function(){autoPlacePhoto(photoLoadSeq);});
[cameraInput,uploadInput].forEach(function(input){listen(input,'change',function(){if(input.files?.[0])activatePhoto(input.files[0],input===cameraInput);});});
listen(cameraVideo,'touchstart',beginCameraPinch,{passive:false});listen(cameraVideo,'touchmove',moveCameraPinch,{passive:false});
listen(cameraVideo,'touchend',endCameraPinch,{passive:true});listen(cameraVideo,'touchcancel',endCameraPinch,{passive:true});
listen(overlay,'click',function(e){if(e.target===overlay)closeDialog();});
listen(document,'keydown',function(e){
 if(overlay.hidden||drawerIsOpen(cartDrawer()))return;if(e.key==='Escape'){e.preventDefault();if(!downloadGate.hidden)closeDownloadGate();else closeDialog();return;}
 if(e.key!=='Tab')return;
 var items=Array.from((!downloadGate.hidden?downloadGate:overlay).querySelectorAll('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled])')).filter(function(n){return n.getClientRects().length;});
 var first=items[0],last=items[items.length-1];
 if(first&&(!overlay.contains(document.activeElement)||(e.shiftKey&&document.activeElement===first)||(!e.shiftKey&&document.activeElement===last))){e.preventDefault();(e.shiftKey?last:first).focus();}
});
listen(window,'resize',fitPreview,{passive:true});
sizeButtons.forEach(function(button){listen(button,'click',function(){selectSizeButton(button,true);});});
listen(skipScale,'click',skipTrueScale);listen(scaleCancel,'click',cancelPointSelection);listen(scaleStart,'click',startPointSelection);
listen(root.querySelector('[data-sc-wall-submit-measurement]'),'click',submitMeasurement);
listen(referenceMeasurement,'keydown',function(e){if(e.key==='Enter'){e.preventDefault();submitMeasurement();}});
listen(root.querySelector('[data-sc-wall-unit-select]'),'change',function(e){var prior=state.unit,next=e.target.value;if(state.referenceMeasurement&&prior!==next)state.referenceMeasurement=next==='in'?state.referenceMeasurement/2.54:state.referenceMeasurement*2.54;setUnit(next);});
listen(stage,'pointerdown',stageCalibrationTap);listen(artCanvas,'pointerdown',beginDrag);listen(artCanvas,'pointermove',moveDrag);listen(artCanvas,'pointerup',endDrag);listen(artCanvas,'pointercancel',endDrag);listen(artCanvas,'lostpointercapture',endDrag);
listen(stickySecure,'click',addSelectedVariantToCart);
var lastPreviewToolTouchAt=0;
function handlePreviewToolActivation(event){
var target=event.target&&event.target.closest?event.target.closest('[data-sc-wall-save],[data-sc-wall-share-preview]'):null;
if(!target||target.disabled||overlay.hidden||!overlay.contains(target)) return;
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
function shieldPreviewToolPointer(event){var target=event.target&&event.target.closest?event.target.closest('[data-sc-wall-save],[data-sc-wall-share-preview],[data-sc-wall-close],[data-sc-wall-download-close]'):null;if(target&&!overlay.hidden&&overlay.contains(target))event.stopImmediatePropagation();}
listen(window,'pointerdown',shieldPreviewToolPointer,true);
listen(window,'pointerup',shieldPreviewToolPointer,true);

listen(downloadConfirm,'click',downloadConfirmedPreview);listen(window,'click',function(event){var target=event.target.closest?.('[data-sc-wall-download-close]');if(!target||overlay.hidden||!overlay.contains(target))return;event.preventDefault();event.stopImmediatePropagation();closeDownloadGate();closeButton.focus({preventScroll:true});},true);
listen(document,'change',function(e){var picker=productPickerFor(root);if(!picker||!picker.contains(e.target)||!e.target.matches('input[type="radio"],select'))return;invalidateComposite();syncFromProductPage();setStickyCartState();});
listen(document,'cart:close',clearCartLayerIfClosed);listen(document,'dispatch:cart-drawer:close',clearCartLayerIfClosed);
renderSizeButtons();

if(window.ResizeObserver){layoutObserver=new ResizeObserver(fitPreview);layoutObserver.observe(modal);}
listen(document,'visibilitychange',function(){if(document.hidden&&cameraStream){stopLiveCamera();intro.hidden=false;}});
listen(window,'pagehide',closeDialog);

}
document.addEventListener('sc:wall-preview:hydrate',function(event){init(event.detail.root);});
document.querySelectorAll(ROOT_SELECTOR).forEach(init);
document.addEventListener('shopify:section:load',function(){document.querySelectorAll(ROOT_SELECTOR).forEach(init);});
document.addEventListener('shopify:section:unload',function(event){event.target.querySelectorAll(ROOT_SELECTOR).forEach(function(root){if(root.scWallDestroy)root.scWallDestroy();});});
}());





