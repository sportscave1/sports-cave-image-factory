/* Saved previews stay lightweight. Exact WEBP downloads are fetched only on click. */
window.ProductUploadPackage = function({request, resize}) {
 const $=id=>document.getElementById(id);
 let key='',generation=0,disposed=false,controller=new AbortController();
 const timers=new Map(),sources=new Map(),objectURLs=new Set();
 const active=current=>{if(disposed||current!==generation||controller.signal.aborted)throw new Error('Selection changed. Download the current image.');};
 function reset(){
  generation++;controller.abort();controller=new AbortController();
  for(const timer of timers.values())clearTimeout(timer);timers.clear();sources.clear();
  for(const url of objectURLs)URL.revokeObjectURL(url);objectURLs.clear();key='';
  $('saved-package').hidden=true;$('package-error').textContent='';$('saved-files').replaceChildren();resize();
 }
 async function source(item,current){
  active(current);const cached=sources.get(item.download);
  if(cached&&cached.expires>Date.now())return cached.blob;
  if(!item.name||!/\.webp$/i.test(item.name)||/[\\/]/.test(item.name))throw new Error('Original WEBP filename unavailable. Retry Save all.');
  const response=await fetch(item.download,{credentials:'same-origin',cache:'no-store',signal:controller.signal});
  if(!response.ok)throw new Error('Saved original unavailable. Retry Save all.');
  const blob=await response.blob();active(current);
  if(blob.type.split(';')[0]!=='image/webp'||blob.size!==item.size)throw new Error('Original WEBP type or size differs. Retry Save all.');
  const bytes=new Uint8Array(await blob.arrayBuffer());active(current);
  const text=(start,end)=>String.fromCharCode(...bytes.subarray(start,end));
  if(bytes.length<20||text(0,4)!=='RIFF'||text(8,12)!=='WEBP'||
     !['VP8 ','VP8L','VP8X'].includes(text(12,16))||new DataView(bytes.buffer).getUint32(4,true)+8!==bytes.length){
   throw new Error('Saved file is not a valid WEBP. Retry Save all.');
  }
  // Dropbox content hashes: SHA-256 of concatenated SHA-256 digests of 4 MiB blocks.
  const blocks=[];for(let at=0;at<bytes.length;at+=4194304){
   blocks.push(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes.subarray(at,at+4194304))));active(current);
  }
  const joined=new Uint8Array(blocks.length*32);blocks.forEach((block,i)=>joined.set(block,i*32));
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',joined)),b=>b.toString(16).padStart(2,'0')).join('');active(current);
  if(digest!==item.content_hash)throw new Error('Saved WEBP bytes differ from the save receipt. Retry Save all.');
  sources.set(item.download,{blob,expires:Date.now()+300000});return blob;
 }
 function card(item,current){
  const card=document.createElement('div');card.className='saved-card';
  const a=document.createElement('a');a.href=item.original;a.target='_blank';a.rel='noopener';a.title=item.name;a.setAttribute('aria-label','Open '+item.label+' original');
  const img=document.createElement('img');img.src=item.preview;img.alt=item.label;img.loading='lazy';img.onload=resize;
  img.onerror=()=>{img.hidden=true;const note=document.createElement('small');note.textContent='Preview unavailable · open original';a.append(note);resize();};a.append(img);
  const caption=document.createElement('span');caption.textContent=item.label;caption.title=item.name;
  const format=document.createElement('small');format.textContent='WEBP';
  // An image MIME write (or a custom format) cannot prove an exact named file paste.
  // Keep this honest even if a future browser advertises image/webp pixel support.
  const copy=document.createElement('button');copy.type='button';copy.className='saved-copy';copy.textContent='Copy unavailable';copy.disabled=true;
  copy.title='Exact WEBP file attachment copying is unavailable in this browser. Download WEBP, then drag the file into ChatGPT.';
  copy.setAttribute('aria-label','Exact WEBP file copying unavailable for '+item.label);
  const button=document.createElement('button');button.type='button';button.className='saved-download';button.textContent='Download WEBP';button.setAttribute('aria-label','Download '+item.label+' WEBP');
  const status=document.createElement('small');status.className='saved-copy-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  let downloadURL='';
  button.onclick=async()=>{
   if(button.disabled||current!==generation||disposed)return;
   clearTimeout(timers.get(button));timers.delete(button);if(downloadURL){URL.revokeObjectURL(downloadURL);objectURLs.delete(downloadURL);downloadURL='';}button.disabled=true;button.textContent='Downloading…';status.textContent='';resize();
   try{
    const blob=await source(item,current);active(current);
    const url=URL.createObjectURL(blob);downloadURL=url;objectURLs.add(url);
    const download=document.createElement('a');download.href=url;download.download=item.name;download.hidden=true;
    document.body.append(download);try{active(current);download.click();}finally{download.remove();}
    // The original Blob is downloaded as-is, with its receipt filename; no canvas or re-encoding.
    button.textContent='Download started';
    timers.set(button,setTimeout(()=>{timers.delete(button);URL.revokeObjectURL(url);objectURLs.delete(url);downloadURL='';if(current===generation&&!disposed){button.textContent='Download WEBP';resize();}},2000));
   }catch(e){if(current===generation&&!disposed){button.textContent='Download WEBP';status.textContent=e.message||'Could not download WEBP. Retry.';}}
   finally{if(current===generation&&!disposed){button.disabled=false;resize();}}
  };
  card.append(a,copy,button,caption,format,status);return card;
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
