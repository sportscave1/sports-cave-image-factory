/* Saved previews stay lightweight. Clipboard sources are fetched only on click. */
window.ProductUploadPackage = function({request, resize}) {
 const $=id=>document.getElementById(id);
 let key='',generation=0,disposed=false,controller=new AbortController();
 const timers=new Map(),sources=new Map();
 const active=current=>{if(disposed||current!==generation||controller.signal.aborted)throw new Error('Selection changed. Copy the current image.');};
 function reset(){
  generation++;controller.abort();controller=new AbortController();
  for(const timer of timers.values())clearTimeout(timer);timers.clear();sources.clear();key='';
  $('saved-package').hidden=true;$('package-error').textContent='';$('saved-files').replaceChildren();resize();
 }
 async function source(item,current){
  active(current);const cached=sources.get(item.original);
  if(cached&&cached.expires>Date.now())return cached.blob;
  const response=await fetch(item.original,{credentials:'same-origin',cache:'no-store',signal:controller.signal});
  if(!response.ok)throw new Error('Saved original unavailable. Retry Save all.');
  const blob=await response.blob();active(current);
  if(blob.type.split(';')[0]!=='image/webp'||!blob.size)throw new Error('Saved WEBP unavailable. Retry Save all.');
  sources.set(item.original,{blob,expires:Date.now()+300000});return blob;
 }
 async function pixels(item,current,type){
  const blob=await source(item,current);active(current);
  if(type==='image/webp')return blob;
  // Match the existing individual-image copy: decode original pixels at natural size.
  const bitmap=await createImageBitmap(blob);
  try{
   active(current);const canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;
   canvas.getContext('2d').drawImage(bitmap,0,0);
   const png=await new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(new Error('PNG conversion failed.')),'image/png'));
   active(current);return png;
  }finally{bitmap.close();}
 }
 function card(item,current){
  const card=document.createElement('div');card.className='saved-card';
  const a=document.createElement('a');a.href=item.original;a.target='_blank';a.rel='noopener';a.title=item.name;a.setAttribute('aria-label','Open '+item.label+' original');
  const img=document.createElement('img');img.src=item.preview;img.alt=item.label;img.loading='lazy';img.onload=resize;
  img.onerror=()=>{img.hidden=true;const note=document.createElement('small');note.textContent='Preview unavailable · open original';a.append(note);resize();};a.append(img);
  const caption=document.createElement('span');caption.textContent=item.label;caption.title=item.name;
  const format=document.createElement('small');format.textContent='WEBP';
  const button=document.createElement('button');button.type='button';button.className='saved-copy';button.textContent='Copy';button.setAttribute('aria-label','Copy '+item.label);
  const status=document.createElement('small');status.className='saved-copy-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  button.onclick=async()=>{
   if(button.disabled||current!==generation||disposed)return;
   clearTimeout(timers.get(button));timers.delete(button);button.disabled=true;button.textContent='Copying…';status.textContent='';resize();
   try{
    if(!window.isSecureContext||!navigator.clipboard?.write||typeof ClipboardItem!=='function')throw new Error('Image clipboard unavailable. Use a supported secure browser.');
    const type=ClipboardItem.supports?.('image/webp')?'image/webp':'image/png';
    // Write synchronously within the click; the promise supplies bytes after retrieval.
    const image=pixels(item,current,type);image.catch(()=>{});
    await navigator.clipboard.write([new ClipboardItem({[type]:image})]);active(current);
    button.textContent='Copied ✓';
    status.textContent=type==='image/png'?'Full-size PNG copied; saved WEBP unchanged.':'WEBP image copied.';
    timers.set(button,setTimeout(()=>{timers.delete(button);if(current===generation&&!disposed){button.textContent='Copy';status.textContent='';resize();}},2000));
   }catch(e){if(current===generation&&!disposed){button.textContent='Copy';status.textContent=e.name==='NotAllowedError'?'Allow clipboard access and retry.':e.message||'Could not copy image. Retry.';}}
   finally{if(current===generation&&!disposed){button.disabled=false;resize();}}
  };
  card.append(a,button,caption,format,status);return card;
 }
 async function sync(row,visible,revision){
  const next=visible&&row?.id&&row.saved_package_version?row.id+':'+row.saved_package_version:'';
  if(!next){if(key)reset();return;}if(key===next)return;reset();key=next;const current=generation;
  try{
   const result=await request('saved-package?id='+encodeURIComponent(row.id));active(current);
   $('saved-package').hidden=false;
   for(const item of result.items)$('saved-files').append(card(item,current));resize();
  }catch(e){if(current===generation&&!disposed){$('package-error').textContent=e.message;$('saved-package').hidden=false;
   const retry=document.createElement('button');retry.textContent='Retry saved files';retry.onclick=()=>{key='';sync(row,true,revision);};$('saved-files').append(retry);resize();}}
 }
 function dispose(){disposed=true;reset();}
 addEventListener('pagehide',dispose);
 try{const frame=window.frameElement;if(frame){const observer=new MutationObserver(()=>{if(!frame.isConnected){dispose();observer.disconnect();}});observer.observe(window.parent.document,{childList:true,subtree:true});}}catch{}
 return {sync,reset,dispose};
};
