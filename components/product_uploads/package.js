/* Exact saved package; the browser never masquerades links/PNG as WebP files. */
window.ProductUploadPackage = function({request, resize}) {
  const $=id=>document.getElementById(id), button=$('copy-files'), label=button.innerHTML;
  let key='',version='',generation=0,pack=null,timer=null,pending=null,bridge=null,disposed=false,nativeAvailable=false,launchCode=null,pollTimer=null,pollReject=null;
  const restore=()=>{clearTimeout(timer);timer=null;button.innerHTML=label;};
  function native(action, transfer) {
    return new Promise((resolve,reject)=>{
      if(!bridge)return reject(Error('Open Product Uploads in the updated Sports Cave Windows desktop app to copy all WebP files.'));
      const request_id=crypto.randomUUID();
      const done=(error,value)=>{clearTimeout(timeout);bridge.removeEventListener('message',receive);pending=null;error?reject(error):resolve(value);};
      const receive=event=>{const m=event.data;if(m?.type!=='sports-cave-desktop'||m.request_id!==request_id||m.action==='progress')return;
        if(m.action==='cancel')return;done(m.ok?null:Error(m.message||m.error||'Windows could not prepare the files. Retry.'),m);};
      const timeout=setTimeout(()=>{bridge.postMessage({action:'cancel',request_id});done(Error('Desktop did not respond. Open the desktop app and retry.'));},action==='hello'?1500:180000);
      pending=()=>{bridge.postMessage({action:'cancel',request_id});done(Error('Upload changed. Copy the current saved package.'));};
      bridge.addEventListener('message',receive);bridge.postMessage({action,request_id,...(transfer?{transfer}:{})});
    });
  }
  function stopLaunch(){clearTimeout(pollTimer);pollTimer=null;if(pollReject){pollReject(Error('Copy cancelled. Click Copy all WEBP files to retry.'));pollReject=null;}if(launchCode){request('clipboard-status',{code:launchCode,cancel:true}).catch(()=>{});launchCode=null;}$('open-copy-helper').hidden=true;$('cancel-copy').hidden=true;}
  function reset(){generation++;if(pending)pending();stopLaunch();restore();pack=null;key='';version='';button.disabled=false;$('saved-package').hidden=true;$('copy-files').hidden=true;$('package-instruction').hidden=true;$('file-fallback').hidden=true;$('package-error').textContent='';$('saved-files').replaceChildren();resize();}
  async function browserCopy(snapshot,current){
    const launched=await request('clipboard-launch',{id:snapshot.id,version:snapshot.version});
    if(current!==generation){request('clipboard-status',{code:launched.code,cancel:true}).catch(()=>{});throw Error('Upload changed.');}
    launchCode=launched.code;
    const link=$('open-copy-helper');link.href=launched.url;link.hidden=false;
    $('cancel-copy').hidden=false;
    $('package-error').textContent='Allow Sports Cave Windows helper to open. If it does not open, use Open clipboard helper below (version 13 or later).';resize();
    // Keep the upload page in place. A visible link also supports browsers that
    // require a second explicit gesture to open an external application.
    try{link.click();}catch{}
    return new Promise((resolve,reject)=>{
      pollReject=reject;let attempts=0;
      const finish=(error,value)=>{if(current!==generation)return reject(Error('Upload changed.'));clearTimeout(pollTimer);pollTimer=null;pollReject=null;link.hidden=true;error?reject(error):resolve(value);};
      const poll=async()=>{
        try{
          if(current!==generation)return finish(Error('Upload changed.'));
          const result=await request('clipboard-status',{code:launched.code});
          if(current!==generation)return finish(Error('Upload changed.'));
          if(result.state==='Complete'){launchCode=null;$('package-error').textContent='';return finish(null,result);}
          if(result.state==='Failed'||result.state==='Cancelled')return finish(Error(result.error||'Copy cancelled. Retry Copy all WEBP files.'));
          if(result.state==='Preparing'){$('package-error').textContent='Windows is preparing all eight files…';resize();}
          if(++attempts>=210)return finish(Error('No clipboard completion received. Check Windows helper version 13, then retry Copy all WEBP files.'));
          pollTimer=setTimeout(poll,1000);
        }catch(e){finish(e);}
      };poll();
    });
  }
  async function sync(row,visible,revision){
    const next=visible&&row?.id&&row.saved_package_version?row.id+':'+row.saved_package_version:'';
    if(!next){if(key)reset();return;}if(key===next)return;reset();key=next;const current=generation;
    try{
      const result=await request('saved-package?id='+encodeURIComponent(row.id));if(current!==generation||disposed)return;
      pack=result;version=result.version;pack.id=row.id;
      $('saved-package').hidden=false;button.hidden=false;$('package-instruction').hidden=false;
      for(const item of result.items){
        const card=document.createElement('div');card.className='saved-card';
        const a=document.createElement('a');a.href=item.original;a.target='_blank';a.rel='noopener';a.title=item.name;a.setAttribute('aria-label','Open '+item.label+' original');
        const img=document.createElement('img');img.src=item.preview;img.alt=item.label;img.loading='lazy';img.onload=resize;img.onerror=()=>{img.hidden=true;const note=document.createElement('small');note.textContent='Preview unavailable · open original';a.append(note);resize();};a.append(img);
        const caption=document.createElement('span');caption.textContent=item.label;caption.title=item.name;
        const format=document.createElement('small');format.textContent='WEBP';card.append(a,caption,format);$('saved-files').append(card);
      }
      resize();
    }catch(e){if(current===generation){$('package-error').textContent=e.message;$('saved-package').hidden=false;
      const retry=document.createElement('button');retry.textContent='Retry saved files';retry.onclick=()=>{key='';sync(row,true,revision);};$('saved-files').append(retry);resize();}}
  }
  async function prepare(action){
    if(button.disabled||!pack)return;
    const current=generation, snapshot=pack;restore();button.disabled=true;button.textContent='Preparing files…';$('package-error').textContent='';resize();
    try{
      try{bridge=window.top.chrome?.webview;}catch{bridge=null;}
      let reply;
      if(!bridge&&action==='copyWebpPackage')reply=await browserCopy(snapshot,current);
      else{
        const hello=await native('hello');if(!hello.productUploadWebp)throw Error('This desktop helper needs the saved WebP package update. Use Select saved files until it is installed.');
        nativeAvailable=true;
        if(current!==generation)return;
        const grant=await request('saved-transfer',{id:snapshot.id,version:snapshot.version});if(current!==generation)return;
        reply=await native(action,grant.transfer);
      }
      if(current!==generation)return;
      if(reply.count!==snapshot.items.length)throw Error('Windows did not confirm every saved WebP. Retry; no complete copy is confirmed.');
      if(action==='copyWebpPackage'){button.textContent='Copied';timer=setTimeout(()=>{restore();resize();},2000);}
      else restore();
    }catch(e){if(current===generation){restore();$('package-error').textContent=e.message;$('file-fallback').hidden=false;}}
    finally{if(current===generation){stopLaunch();button.disabled=false;resize();}}
  }
  button.onclick=()=>prepare('copyWebpPackage');
  $('cancel-copy').onclick=()=>stopLaunch();
  $('select-files').onclick=async()=>{
    if(!pack)return;
    if(nativeAvailable)return prepare('selectWebpPackage');
    // Browser fallback lists only this receipt's exact files. No folder navigation.
    const list=$('attachment-files');list.replaceChildren();list.hidden=false;
    for(const item of pack.items){const a=document.createElement('a');a.href=item.download;a.textContent=item.name;a.download=item.name;list.append(a);}
    $('attachment-help').textContent='Download these exact WebPs, then select all eight in ChatGPT’s attachment picker. Browser clipboard cannot attach this multi-file package. Paste the files before copying the prompt.';
    resize();
  };
  function dispose(){disposed=true;reset();}
  addEventListener('pagehide',dispose);
  // Streamlit can remove an iframe without a pagehide event.
  try{const frame=window.frameElement;if(frame){const observer=new MutationObserver(()=>{if(!frame.isConnected){dispose();observer.disconnect();}});observer.observe(window.parent.document,{childList:true,subtree:true});}}catch{}
  return {sync,reset,dispose};
};
