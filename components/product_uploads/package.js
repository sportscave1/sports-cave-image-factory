/* Saved previews and native preparation share one verified, versioned receipt. */
window.ProductUploadPackage = function({request, resize}) {
 const $=id=>document.getElementById(id),button=$('copy-files'),label=button.innerHTML;
 let key='',generation=0,pack=null,code=null,pollTimer=null,feedback=null,disposed=false,state='',copyStarted=0,seenSequence=0;
 const restore=()=>{clearTimeout(feedback);feedback=null;button.innerHTML=label;};
 function revoke(){clearTimeout(pollTimer);pollTimer=null;if(code){request('clipboard-status',{code,cancel:true}).catch(()=>{});code=null;}}
 function reset(){generation++;revoke();restore();pack=null;key='';state='';button.disabled=true;$('saved-package').hidden=true;button.hidden=true;$('package-instruction').hidden=true;$('file-fallback').hidden=true;$('package-error').textContent='';$('saved-files').replaceChildren();$('open-copy-helper').hidden=true;$('cancel-copy').hidden=true;resize();}
 function failed(message,current){if(current!==generation)return;revoke();state='Failed';restore();button.disabled=false;button.textContent='Retry file preparation';$('package-error').textContent=message;$('open-copy-helper').hidden=true;$('cancel-copy').hidden=true;resize();}
 async function start(current){
  seenSequence=0;state='Preparing';button.disabled=true;button.textContent='Preparing files…';$('package-error').textContent='';resize();
  try{
   const launched=await request('clipboard-launch',{id:pack.id,version:pack.version});
   if(current!==generation||disposed){request('clipboard-status',{code:launched.code,cancel:true}).catch(()=>{});return;}
   code=launched.code;const link=$('open-copy-helper');link.href=launched.url;link.textContent='Connect Windows file clipboard';link.hidden=false;$('cancel-copy').hidden=false;
   $('package-error').textContent='Allow the Windows helper to prepare these files. If it does not open, use Connect Windows file clipboard.';
   try{link.click();}catch{ /* Explicit link remains available when browser blocks an automatic launch. */ }
   let waiting=0;
   const poll=async()=>{
    try{
     const result=await request('clipboard-status',{code:launched.code});if(current!==generation||disposed)return;
     state=result.state;
     if(state==='Failed'||state==='Cancelled')return failed(result.error||'Preparation cancelled. Retry when ready.',current);
     if(state==='Ready'||state==='Complete'){
      link.hidden=true;$('cancel-copy').hidden=true;$('package-error').textContent='';button.disabled=false;
      if(state==='Complete'&&result.sequence>seenSequence){
       seenSequence=result.sequence;clearTimeout(feedback);button.textContent='Copied '+result.count+' files ✓';
       button.dataset.copyMs=String(Math.round(performance.now()-copyStarted));button.dataset.nativeCopyMs=String(result.copy_ms??'');
       feedback=setTimeout(()=>{restore();resize();},2000);
      }else if(!feedback)restore();
     }else{button.disabled=true;button.textContent=(state==='CopyRequested'||state==='Copying')?'Copying files…':'Preparing files…';
      if(state==='Preparing'){$('package-error').textContent='Preparing all eight saved WebPs. The clipboard is unchanged.';link.hidden=true;}
      if(state==='Waiting'&&++waiting>120)return failed('Windows helper did not connect. Open the updated helper and retry preparation.',current);
     }
     resize();pollTimer=setTimeout(poll,(state==='CopyRequested'||state==='Copying')?150:750);
    }catch(e){failed(e.message,current);}
   };poll();
  }catch(e){failed(e.message,current);}
 }
 async function sync(row,visible,revision){
  const next=visible&&row?.id&&row.saved_package_version?row.id+':'+row.saved_package_version:'';
  if(!next){if(key)reset();return;}if(key===next)return;reset();key=next;const current=generation;
  try{
   const result=await request('saved-package?id='+encodeURIComponent(row.id));if(current!==generation||disposed)return;
   pack={...result,id:row.id};$('saved-package').hidden=false;button.hidden=false;$('package-instruction').hidden=false;
   for(const item of result.items){
    const card=document.createElement('div');card.className='saved-card';
    const a=document.createElement('a');a.href=item.original;a.target='_blank';a.rel='noopener';a.title=item.name;a.setAttribute('aria-label','Open '+item.label+' original');
    const img=document.createElement('img');img.src=item.preview;img.alt=item.label;img.loading='lazy';img.onload=resize;img.onerror=()=>{img.hidden=true;const note=document.createElement('small');note.textContent='Preview unavailable · open original';a.append(note);resize();};a.append(img);
    const caption=document.createElement('span');caption.textContent=item.label;caption.title=item.name;
    const format=document.createElement('small');format.textContent='WEBP';card.append(a,caption,format);$('saved-files').append(card);
   }
   resize();await start(current);
  }catch(e){if(current===generation){$('package-error').textContent=e.message;$('saved-package').hidden=false;
   const retry=document.createElement('button');retry.textContent='Retry saved files';retry.onclick=()=>{key='';sync(row,true,revision);};$('saved-files').append(retry);resize();}}
 }
 button.onclick=async()=>{
  if(button.disabled||!pack)return;const current=generation;
  if(state==='Failed')return start(current);
  restore();button.disabled=true;button.textContent='Copying files…';copyStarted=performance.now();resize();
  try{await request('clipboard-status',{code,copy:true});}catch(e){failed(e.message,current);}
 };
 $('cancel-copy').onclick=()=>failed('Preparation cancelled. Retry when ready.',generation);
 function dispose(){disposed=true;reset();}
 addEventListener('pagehide',dispose);
 try{const frame=window.frameElement;if(frame){const observer=new MutationObserver(()=>{if(!frame.isConnected){dispose();observer.disconnect();}});observer.observe(window.parent.document,{childList:true,subtree:true});}}catch{}
 return {sync,reset,dispose};
};
