/* An authenticated, expiring capability scopes this window to one saved package. */
(async()=>{
 const status=document.getElementById('status'),code=location.hash.slice(1);
 history.replaceState(null,'',location.pathname);
 const bridge=window.chrome?.webview;let cancel=null,receipt=null,closed=false,heartbeat=null;
 async function post(action,body){const response=await fetch('/api/product-uploads/clipboard-'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'});const result=await response.json();if(!response.ok)throw Error(result.error||'Clipboard service unavailable. Retry from Product Uploads.');return result;}
 function native(action,transfer){return new Promise((resolve,reject)=>{
  const request_id=crypto.randomUUID();
  const finish=(error,value)=>{clearTimeout(timer);bridge.removeEventListener('message',receive);cancel=null;error?reject(error):resolve(value);};
  const receive=e=>{const m=e.data;if(m?.type!=='sports-cave-desktop'||m.request_id!==request_id||m.action==='progress'||m.action==='cancel')return;finish(m.ok?null:Error(m.message||m.error||'Windows could not prepare the files.'),m);};
  const timer=setTimeout(()=>{bridge.postMessage({action:'cancel',request_id});finish(Error('Windows timed out. Retry preparation.'));},180000);
  cancel=()=>{bridge.postMessage({action:'cancel',request_id});finish(Error('File preparation cancelled. Retry from Product Uploads.'));};
  bridge.addEventListener('message',receive);bridge.postMessage({action,request_id,...(transfer?{transfer}:{})});
 });}
 const report=(event,extra={})=>post('complete',{code,secret:receipt.secret,event,...extra});
 addEventListener('pagehide',()=>{closed=true;clearInterval(heartbeat);if(cancel)cancel();});
 try{
  if(!/^[A-Za-z0-9_-]{43}$/.test(code))throw Error('This preparation link is invalid or expired. Retry from Product Uploads.');
  if(!bridge)throw Error('Open preparation with the Sports Cave Windows helper.');
  const hello=await native('hello');if(!hello.productUploadPreparedWebp)throw Error('Windows helper update required for background preparation.');
  status.textContent='Preparing all eight saved WebP files…';
  receipt=await post('claim',{code});
  heartbeat=setInterval(()=>report('heartbeat').catch(e=>{closed=true;if(cancel)cancel();status.textContent=e.message;}),3000);
  const prepared=await native('prepareWebpPackage',receipt.transfer);
  await report('ready',{count:prepared.count});
  status.textContent='All eight files ready. Return to Product Uploads and click Copy all WEBP files. Keep this helper window open.';
  while(!closed){
   const command=await report('poll');
   if(command.command==='copy'){
    status.textContent='Copying prepared files…';
    const result=await native('copyPreparedWebpPackage',receipt.transfer);
    if(result.count!==8)throw Error('Windows did not verify all eight clipboard files. Retry.');
    await report('complete',{sequence:command.sequence,count:result.count,copy_ms:result.copy_ms});
    status.textContent='✓ Copied eight files. Paste into ChatGPT before copying the upload prompt. You can copy again from Product Uploads.';
   }
   await new Promise(resolve=>setTimeout(resolve,150));
  }
 }catch(error){status.textContent=error.message;if(receipt)try{await report('failed',{error:error.message});}catch{}}
 finally{clearInterval(heartbeat);}
})();
