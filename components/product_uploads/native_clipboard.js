/* This page accepts only a short-lived one-use server capability in its fragment. */
(async()=>{
 const status=document.getElementById('status'),code=location.hash.slice(1);
 history.replaceState(null,'',location.pathname);
 const bridge=window.chrome?.webview;let cancel=null,receipt=null;
 async function post(action,body){const response=await fetch('/api/product-uploads/clipboard-'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'});const result=await response.json();if(!response.ok)throw Error(result.error||'Clipboard service unavailable. Retry from Product Uploads.');return result;}
 function native(action,transfer){return new Promise((resolve,reject)=>{
  const request_id=crypto.randomUUID();
  const finish=(error,value)=>{clearTimeout(timer);bridge.removeEventListener('message',receive);cancel=null;error?reject(error):resolve(value);};
  const receive=e=>{const m=e.data;if(m?.type!=='sports-cave-desktop'||m.request_id!==request_id||m.action==='progress'||m.action==='cancel')return;finish(m.ok?null:Error(m.message||m.error||'Windows could not copy the files.'),m);};
  const timer=setTimeout(()=>{bridge.postMessage({action:'cancel',request_id});finish(Error('Windows timed out. Retry Copy all WEBP files.'));},180000);
  cancel=()=>{bridge.postMessage({action:'cancel',request_id});finish(Error('Clipboard preparation cancelled. Retry from Product Uploads.'));};
  bridge.addEventListener('message',receive);bridge.postMessage({action,request_id,...(transfer?{transfer}:{})});
 });}
 addEventListener('pagehide',()=>{if(cancel)cancel();});
 try{
  if(!/^[A-Za-z0-9_-]{43}$/.test(code))throw Error('This copy link is invalid or expired. Click Copy all WEBP files again.');
  if(!bridge)throw Error('Open this request with Sports Cave Windows helper version 13 or later.');
  const hello=await native('hello');if(!hello.productUploadWebp)throw Error('Update the Sports Cave Windows helper, then retry.');
  status.textContent='Preparing all eight saved WebP files…';
  receipt=await post('claim',{code});
  const result=await native('copyWebpPackage',receipt.transfer);
  if(result.count!==8)throw Error('Windows did not confirm all eight files. Retry from Product Uploads.');
  await post('complete',{code,secret:receipt.secret,count:result.count});
  status.textContent='✓ Copied all eight WebP files. Paste into ChatGPT now. You can close this window and copy again whenever needed.';
 }catch(error){status.textContent=error.message;if(receipt)try{await post('complete',{code,secret:receipt.secret,count:0,error:error.message});}catch{}}
})();
