/* Small binary chunks, one upload loop, account-scoped durable backend state. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),CHUNK=4*1024*1024,labels={DRAFT:'Upload to Draft',LIVE:'Upload to Live',UPDATE:'Update Existing'};
  let row=null,manual=false,enabled=true,busy=false,timer=null,previewTimer=null,previewAttempts=0,previewKey='',previewBlob='',promptText='',copyMode='',copyID='',stopped=false,epoch=0,section='full',component=false,activeID='',refreshKey='',controller=new AbortController();
  // Resume identity is separate from the visible page selection. Never restore a row on load.
  const RESUME_KEY='sports-cave-product-upload-resume-v1',hashes=new WeakMap();
  let selectedFile=null,transfer=null,lastHeight=0,transferTimer=null;
  const metrics=window.productUploadMetrics={requests:[],identity:[],note:'Request time includes browser transfer and storage acknowledgement; server durations are nested.'};
  function record(list,value){list.push(value);if(list.length>100)list.shift();}
  function resumeMeta(){try{return JSON.parse(sessionStorage.getItem(RESUME_KEY)||'null');}catch{return null;}}
  function saveResume(value){try{sessionStorage.setItem(RESUME_KEY,JSON.stringify(value));}catch{}}
  function forgetResume(){try{sessionStorage.removeItem(RESUME_KEY);}catch{}}
  const abortError=()=>Object.assign(new Error('Upload cancelled'),{name:'AbortError'});
  function pause(ms){return new Promise((resolve,reject)=>{const signal=controller.signal;const done=()=>{signal.removeEventListener('abort',cancel);resolve();};const timer=setTimeout(done,ms);const cancel=()=>{clearTimeout(timer);reject(abortError());};signal.addEventListener('abort',cancel,{once:true});if(signal.aborted)cancel();});}
  function paintTransfer(){
    if(!row||row.basic_validated||!transfer)return;
    const saved=row.offset||0,elapsed=(Date.now()-transfer.started)/1000,speed=elapsed>0?(saved-transfer.initial)/elapsed:0,percent=100*saved/row.size;
    $('stage').textContent=transfer.phase;
    $('progress').value=percent;
    const rate=speed>0?`${(speed/1048576).toFixed(2)} MiB/s`:'Measuring speed';
    const eta=speed>0&&transfer.phase==='Uploading'?`${Math.ceil((row.size-saved)/speed)}s remaining`:'ETA pending';
    $('detail').textContent=`${(saved/1048576).toFixed(1)} / ${(row.size/1048576).toFixed(1)} MiB saved · ${percent.toFixed(1)}% · ${rate} · ${eta}`+
      (transfer.phase==='Retrying'?` · Retrying in ${Math.max(0,Math.ceil((transfer.retryAt-Date.now())/1000))}s; the selected PSD is retained.`:
       transfer.phase==='Interrupted'?' · PSD retained. Retry upload to continue from the saved offset.':
       transfer.phase==='Processing'?' · Transfer complete; verifying saved PSD.':
       transfer.sent>0?` · ${(transfer.sent/1048576).toFixed(1)} MiB sent in this request; awaiting storage acknowledgement.`:'');
  }
  const notify=()=>{if(component)parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',value:{id:row?.id||null,manual,mode:$('mode').value,visible:!document.hidden,linked:!!row?.product_title,nonce:crypto.randomUUID()},dataType:'json'},'*');};
  function reset(){stopped=false;clearTimeout(transferTimer);selectedFile=null;transfer=null;epoch++;controller.abort();controller=new AbortController();row=null;busy=false;promptText='';copyID='';copyMode='';clearTimeout(timer);clearTimeout(previewTimer);previewKey='';previewAttempts=0;if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob='';$('file').value='';$('product').value='';$('filename').textContent='';$('stage').textContent='';$('detail').textContent='';$('choices').replaceChildren();$('preview').textContent='Preview pending';$('fallback').close();clear();render();notify();}
  const fail=e=>{if(e.name==='AbortError')return;$('error').textContent=e.message||String(e);$('error').hidden=false;};
  const clear=()=>{$('error').hidden=true;};
  async function request(path,body,raw){
    const generation=epoch,started=Date.now(),signal=controller.signal;
    let response,browserSendMs=null;
    const recordFailure=error=>record(metrics.requests,{operation:path.split('?')[0],bytes:raw?body.size:0,elapsed_ms:Date.now()-started,browser_send_ms:browserSendMs,status:0,error});
    if(raw){
      // XHR exposes actual browser bytes sent. Confirmed progress advances only after storage ACK.
      response=await new Promise((resolve,reject)=>{
        const xhr=new XMLHttpRequest();
        let idleTimer=null,lastSent=0,deadlineReason='';
        const expire=reason=>{deadlineReason=reason;xhr.abort();};
        const arm=ms=>{clearTimeout(idleTimer);idleTimer=setTimeout(()=>expire('progress'),ms);};
        const cancel=()=>xhr.abort();
        const cleanup=()=>{clearTimeout(idleTimer);signal.removeEventListener('abort',cancel);};
        const timeoutError=()=>Object.assign(new Error('Upload progress or acknowledgement timed out. Reconciling saved bytes before retry.'),{retryable:true,slow:true});
        xhr.open('POST','/api/product-uploads/'+path);xhr.withCredentials=true;xhr.timeout=900000;
        xhr.setRequestHeader('Content-Type','application/octet-stream');
        xhr.upload.onprogress=e=>{if(e.loaded>lastSent){lastSent=e.loaded;arm(e.loaded>=body.size?180000:60000);}if(generation===epoch&&transfer){transfer.sent=e.loaded;if(e.loaded===body.size)browserSendMs=Date.now()-started;paintTransfer();}};
        xhr.onload=()=>{cleanup();resolve({ok:xhr.status>=200&&xhr.status<300,status:xhr.status,json:async()=>JSON.parse(xhr.responseText),headers:{get:name=>xhr.getResponseHeader(name)}});};
        xhr.onerror=()=>{cleanup();recordFailure('network');reject(Object.assign(new Error('Connection interrupted; your saved bytes are retained.'),{retryable:true}));};
        xhr.ontimeout=()=>{cleanup();recordFailure('timeout');reject(timeoutError());};
        xhr.onabort=()=>{cleanup();if(deadlineReason){recordFailure('timeout');reject(timeoutError());}else reject(abortError());};
        signal.addEventListener('abort',cancel,{once:true});if(signal.aborted){cleanup();reject(abortError());return;}arm(60000);xhr.send(body);
      });
    }else{
      const deadline=new AbortController();let timedOut=false;
      const cancel=()=>deadline.abort();signal.addEventListener('abort',cancel,{once:true});
      const timeout=setTimeout(()=>{timedOut=true;deadline.abort();},180000);
      try{response=await fetch('/api/product-uploads/'+path,{credentials:'same-origin',signal:deadline.signal,method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});}
      catch(e){if(signal.aborted)throw abortError();recordFailure(timedOut?'timeout':'network');throw Object.assign(new Error(timedOut?'Upload acknowledgement timed out.':e.message),{retryable:true});}
      finally{clearTimeout(timeout);signal.removeEventListener('abort',cancel);}
    }
    record(metrics.requests,{operation:path.split('?')[0],bytes:raw?body.size:0,elapsed_ms:Date.now()-started,browser_send_ms:browserSendMs,status:response.status,server_timing:response.headers?.get('Server-Timing')||''});
    if(generation!==epoch)throw abortError();
    let value;try{value=await response.json();}catch{throw Object.assign(new Error('Invalid server acknowledgement.'),{retryable:response.ok||response.status>=500});}
    if(!response.ok)throw Object.assign(new Error(response.status===403?'Your session expired or access changed. Sign in again, then retry your saved upload.':value.error||'Request failed; retry.'),{retryable:[408,425,429,500,502,503,504].includes(response.status),retryAfter:Math.min(30000,Math.max(0,Number(response.headers?.get('Retry-After'))*1000))});
    return value;
  }
  async function retryRequest(path,body,raw){
    const phase=transfer?.phase;
    let uncertain=false,slow=false;
    for(let attempt=0;attempt<6;attempt++){
      try{
        if(raw&&uncertain&&row?.relay_resume){
          // This read takes the same DB lease as the relay. It can only return
          // once prior provider writes/checkpoints have settled, including after restart.
          const snapshot=(await request('resume',{id:row.id})).upload;
          if(snapshot?.id!==row.id||snapshot.size!==row.size||!Number.isInteger(snapshot.offset)||snapshot.offset<(row.offset||0)||snapshot.offset>row.size)throw new Error('Invalid saved upload identity or offset.');
          const previousOffset=Number(new URLSearchParams(path.split('?')[1]).get('offset'));
          const end=previousOffset+body.size;
          row=snapshot;if(slow&&transfer)transfer.chunkLimit=CHUNK;
          if(snapshot.offset>=end){paintTransfer();return {upload:snapshot};}
          const limit=transfer?.chunkLimit||CHUNK*2;
          body=selectedFile.slice(snapshot.offset,Math.min(selectedFile.size,snapshot.offset+limit));
          path=`chunk?id=${encodeURIComponent(row.id)}&offset=${snapshot.offset}`;
          uncertain=false;paintTransfer();
        }
        const result=await request(path,body,raw);
        if(raw){
          const at=Number(new URLSearchParams(path.split('?')[1]).get('offset')),saved=result.upload;
          if(saved?.id!==row.id||saved.size!==row.size||!Number.isInteger(saved.offset)||saved.offset<at+body.size||saved.offset>row.size)throw new Error('Invalid saved upload acknowledgement.');
        }
        return result;
      }catch(e){
        if(e.name==='AbortError'||!e.retryable||attempt===5)throw e;
        if(raw){uncertain=true;slow=slow||!!e.slow;}
        const delay=e.retryAfter||Math.min(15000,750*2**attempt);
        if(transfer){transfer.phase='Retrying';transfer.retryAt=Date.now()+delay;paintTransfer();}
        await pause(delay);if(transfer){transfer.phase=phase;transfer.sent=0;paintTransfer();}
      }
    }
  }
  const action=(name,extra={})=>request(name,{id:row?.id,mode:$('mode').value,...extra});
  function schedule(){clearTimeout(timer);if(!manual&&row?.basic_validated&&!['Cloud Ready','Failed','Uploaded'].includes(row.state)&&!busy&&!document.hidden&&!stopped)timer=setTimeout(refresh,5000);}
  function render(){
    $('drop').hidden=manual||!!row?.basic_validated;$('manual').textContent=manual&&enabled?'Use automatic workflow':'Use manual workflow';$('manual').disabled=!enabled||busy;
    $('mode').disabled=busy;$('choose').disabled=busy;$('new').hidden=!row||busy;
    $('summary').hidden=manual||!row;if(row){$('filename').textContent=row.name;$('stage').textContent=row.state==='Checking design'?'Processing':row.state;
      $('progress').value=row.size?100*(row.offset||0)/row.size:0;$('progress').hidden=!!row.basic_validated;
      $('detail').textContent=row.reason||(row.basic_validated?'PSD saved and checked. Generate product images below; edition preparation starts after verified Shopify completion.':`${((row.offset||0)/1048576).toFixed(1)} / ${(row.size/1048576).toFixed(1)} MiB saved. Select the original PSD to validate its identity and resume.`);
    }
    paintTransfer();
    $('prompt').hidden=!(manual||row?.basic_validated);$('action-label').textContent=labels[$('mode').value];$('copy').disabled=busy||(!manual&&!!row?.product_title);
    $('return').hidden=manual||!row?.copied;$('upload').disabled=busy||!!row?.product_title;$('upload').textContent=row?.product_title?'Linked':'Upload';$('product').readOnly=!!row?.product_title;
    if(row?.lookup&&!$('product').value)$('product').value=row.lookup;
    $('choices').replaceChildren();for(const p of row?.choices||[]){const b=document.createElement('button');b.textContent=`${p.title} · ${p.status} · ${p.handle} · ${p.id.split('/').pop()}`;b.onclick=()=>link(p.id);$('choices').append(b);}
    $('terminal').hidden=manual||!row?.product_title;$('terminal').textContent=row?.product_title?`${row.shopify_completion||'Shopify product verified'} · Linked to ${row.product_title} · ${row.state}${row.reason?' — '+row.reason:''}`:'';
    const retryUpload=!!selectedFile&&transfer?.phase==='Interrupted';
    $('retry').hidden=manual||(!retryUpload&&(row?.state!=='Failed'||!row?.product_title));$('retry').textContent=retryUpload?'Retry upload':'Retry preparation';
    if(previewKey&&previewKey!==row?.preview_url){clearTimeout(previewTimer);previewKey='';previewAttempts=0;if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob='';$('preview').textContent='Preview pending';}
    if(row?.basic_validated&&!row.preview_url)$('preview').textContent=row.state==='Failed'?'Preview unavailable':row.product_title?'Preview waiting':'PSD saved';
    if(row?.preview_url&&previewKey!==row.preview_url)loadPreview(row.preview_url);
    $('remove').hidden=!row;
    if(section==='upload'){$('prompt').hidden=true;$('return').hidden=true;$('terminal').hidden=true;$('retry').hidden=!(selectedFile&&transfer?.phase==='Interrupted');}
    if(section==='handoff'){$('setup').hidden=true;$('automatic').hidden=true;$('footer').hidden=true;$('remove').hidden=true;}
    schedule();resize();
  }
  function resize(){if(parent!==window){const height=Math.ceil(document.body.getBoundingClientRect().height);if(height===lastHeight)return;lastHeight=height;parent.postMessage({type:'sports-cave-product-upload-height',height},location.origin);if(component)parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height},'*');}}
  window.addEventListener('message',event=>{if(event.origin===location.origin&&event.source===parent&&event.data?.type==='sports-cave-product-upload-measure')resize();});
  async function refresh(){const current=epoch,requested=row?.id;try{const data=await request('state'+(row?.id?'?id='+encodeURIComponent(row.id):''));if(current!==epoch||requested!==row?.id)return;const previousManual=manual;enabled=data.enabled;row=data.upload;manual=!enabled||manual;if(previousManual!==manual)notify();if(row)$('mode').value=row.mode;render();}catch(e){if(current===epoch&&e.name!=='AbortError')fail(e);clearTimeout(timer);}}
  async function fileHash(file){
    if(hashes.has(file))return hashes.get(file);
    const started=Date.now(),generation=epoch,blocks=[];
    // Dropbox's 4 MiB content-hash identity: one bounded pass, reused on retained-file retries.
    for(let at=0;at<file.size;at+=CHUNK){
      if(generation!==epoch)throw abortError();
      const part=await file.slice(at,at+CHUNK).arrayBuffer();blocks.push(new Uint8Array(await crypto.subtle.digest('SHA-256',part)));
      $('detail').textContent=`Checking exact file identity · ${Math.min(100,100*(at+part.byteLength)/file.size).toFixed(0)}% · No artwork processing`;
    }
    const all=new Uint8Array(blocks.length*32);blocks.forEach((h,i)=>all.set(h,i*32));
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',all))).map(b=>b.toString(16).padStart(2,'0')).join('');
    hashes.set(file,hash);record(metrics.identity,{bytes:file.size,elapsed_ms:Date.now()-started});return hash;
  }
  async function upload(file){
    if(busy||!file)return;const current=epoch;clear();busy=true;clearTimeout(timer);
    try{
      if(!/\.psd$/i.test(file.name)||file.size<40||file.size>1073741824)throw new Error('Choose a layered PSD up to 1 GiB.');
      if(row?.basic_validated)throw new Error('Use Start another upload before selecting a different PSD. Your saved upload is retained.');
      $('summary').hidden=false;$('filename').textContent=file.name;$('stage').textContent='Checking file identity';$('progress').value=0;$('progress').hidden=false;$('detail').textContent='Reading bounded chunks to identify this exact PSD.';$('choose').disabled=true;$('remove').hidden=false;resize();
      const hash=await fileHash(file);if(current!==epoch)return;
      const previous=resumeMeta();
      if(row&&((selectedFile&&hashes.get(selectedFile)!==hash)||(previous?.id===row.id&&previous.hash!==hash)))throw new Error('The selected PSD differs from the saved upload. Retry upload uses the retained original; Start another upload accepts a different file.');
      selectedFile=file;
      // A fresh page stays empty. Only explicit selection + complete identity can reuse a saved intake.
      const id=row?.id||(previous?.name===file.name&&previous?.size===file.size&&previous?.hash===hash?previous.id:crypto.randomUUID());
      saveResume({id,name:file.name,size:file.size,hash});
      transfer={phase:'Uploading',started:Date.now(),initial:row?.offset||0,sent:0};
      if(!row)row={id,mode:$('mode').value,name:file.name,size:file.size,offset:0,state:'Uploading PSD'};
      render();
      const pulse=()=>{if(current!==epoch||!busy)return;paintTransfer();transferTimer=setTimeout(pulse,1000);};pulse();
      const started=await retryRequest('start',{id,mode:$('mode').value,name:file.name,size:file.size,content_hash:hash});if(current!==epoch)return;
      row=started.upload;$('mode').value=row.mode;transfer.initial=row.offset;transfer.phase='Uploading';render();
      while(row.offset<file.size){
        // Negotiate the existing ordered transport; older servers still receive 4 MiB.
        const transport=Math.min(transfer.chunkLimit||2*CHUNK,row.transport_chunk_bytes===2*CHUNK?2*CHUNK:CHUNK);
        const offset=row.offset,chunk=file.slice(offset,Math.min(file.size,offset+transport));
        transfer.phase='Uploading';transfer.sent=0;paintTransfer();
        const result=await retryRequest(`chunk?id=${encodeURIComponent(id)}&offset=${offset}`,chunk,true);
        if(current!==epoch)return;
        const next=result.upload;
        if(next.id!==row.id||next.size!==file.size||!Number.isInteger(next.offset)||next.offset<=offset||next.offset>file.size)throw new Error('Invalid saved upload offset. Retry with the original PSD.');
        row=next;transfer.sent=0;render();
      }
      transfer.phase='Processing';paintTransfer();
      const finished=await retryRequest('finish',{id,mode:$('mode').value});if(current!==epoch)return;
      row=finished.upload;selectedFile=null;transfer=null;forgetResume();notify();
    }catch(e){if(current===epoch&&e.name!=='AbortError'){if(transfer){transfer.phase='Interrupted';transfer.retryable=!!e.retryable;}fail(e);}}
    finally{if(current===epoch){clearTimeout(transferTimer);busy=false;render();$('file').value='';}}
  }
  async function copied(){
    if(copyMode!==$('mode').value||copyID!==(manual?'':row?.id))throw new Error('The selected action changed. Copy the current prompt again.');
    if(!manual)row=(await action('copied')).upload;$('copy').textContent='Copied';$('fallback').close();render();setTimeout(()=>{$('copy').textContent='Copy Prompt';},2200);
  }
  async function copy(){if(busy)return;const current=epoch;busy=true;clear();render();$('copy').textContent='Preparing prompt…';try{promptText=(await action('prompt',{id:manual?null:row?.id})).prompt;if(current!==epoch)return;copyMode=$('mode').value;copyID=manual?'':row?.id;let deadline;try{await Promise.race([navigator.clipboard.writeText(promptText),new Promise((_,reject)=>{deadline=setTimeout(()=>reject(new Error('Clipboard request timed out.')),2500);})]);}catch(e){if(current!==epoch)return;$('fallback-text').value=promptText;$('fallback').showModal();$('fallback-text').select();fail(new Error('Clipboard access was blocked or did not respond. Use the copy fallback to continue.'));return;}finally{clearTimeout(deadline);}if(current!==epoch)return;await copied();}catch(e){fail(e);}finally{if(current!==epoch)return;busy=false;if($('copy').textContent!=='Copied')$('copy').textContent='Copy Prompt';render();}}
  $('fallback-copy').onclick=async()=>{try{$('fallback-text').select();if(!document.execCommand('copy'))throw new Error('Press Ctrl+C while the prompt is selected.');await copied();clear();}catch(e){fail(e);}};
  $('fallback-text').addEventListener('copy',e=>{const t=$('fallback-text');if(e.isTrusted&&t.value.slice(t.selectionStart,t.selectionEnd)===promptText)queueMicrotask(()=>copied().catch(fail));});
  async function link(pid){if(busy)return;const current=epoch;busy=true;clear();render();try{const linked=await action(pid?'link':'resolve',pid?{product_id:pid}:{value:$('product').value});if(current!==epoch)return;row=linked.upload;
    if(row.product_title){notify();parent.postMessage({type:'sports-cave-product-upload-linked'},location.origin);}
  }catch(e){fail(e);}finally{if(current!==epoch)return;busy=false;render();}}
  async function loadPreview(url){const current=epoch;if(stopped||document.hidden||previewAttempts>=12)return;previewKey=url;previewAttempts++;try{const r=await fetch(url,{credentials:'same-origin'});if(current!==epoch)return;if(r.status===202){$('preview').textContent='Preparing preview';previewTimer=setTimeout(()=>{if(row?.preview_url===url)loadPreview(url);},5000);return;}if(!r.ok)throw new Error('Preview unavailable');if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob=URL.createObjectURL(await r.blob());if(row?.preview_url!==url){URL.revokeObjectURL(previewBlob);previewBlob='';return;}const img=new Image();img.alt='Prepared design preview';img.src=previewBlob;$('preview').replaceChildren(img);}catch(e){if(current===epoch)$('preview').textContent='Preview unavailable';}}
  $('choose').onclick=()=>$('file').click();$('file').onchange=()=>upload($('file').files[0]);$('copy').onclick=copy;$('upload').onclick=()=>link();$('close').onclick=()=>$('fallback').close();
  $('mode').onchange=async()=>{clear();try{if(row&&!manual)row=(await action('mode')).upload;$('product').value='';promptText='';render();notify();}catch(e){fail(e);if(row)$('mode').value=row.mode;}};
  $('manual').onclick=()=>{manual=!manual;if(!manual&&row)$('mode').value=row.mode;clear();render();notify();};
  $('new').onclick=()=>{forgetResume();reset();};$('remove').onclick=()=>{forgetResume();reset();};
  $('retry').onclick=async()=>{if(selectedFile&&transfer?.phase==='Interrupted')return upload(selectedFile);try{await action('retry');await refresh();}catch(e){fail(e);}};
  for(const event of ['dragenter','dragover'])$('drop').addEventListener(event,e=>{e.preventDefault();$('drop').classList.add('drag');});
  $('drop').addEventListener('dragleave',()=>$('drop').classList.remove('drag'));$('drop').addEventListener('drop',e=>{e.preventDefault();$('drop').classList.remove('drag');upload(e.dataTransfer.files[0]);});
  window.addEventListener('pageshow',event=>{if(event.persisted)reset();});
  window.addEventListener('message',event=>{if(event.source!==parent||event.data?.type!=='streamlit:render')return;if(!component)lastHeight=0;component=true;const args=event.data.args||{};section=args.section||'full';if(section==='upload'&&args.refresh&&args.refresh!==refreshKey){refreshKey=args.refresh;if(row&&!busy)refresh();}if(section==='handoff'&&args.manual){manual=true;if(args.mode)$('mode').value=args.mode;}if(section==='handoff'&&args.id&&(activeID!==args.id||args.mode&&row?.mode!==args.mode)){activeID=args.id;row={id:args.id};refresh();}render();});
  parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');
  document.addEventListener('visibilitychange',()=>{clearTimeout(timer);clearTimeout(previewTimer);if(section==='upload'&&!busy)notify();if(!document.hidden&&!busy){if(row?.preview_url&&!previewBlob){previewKey='';previewAttempts=0;}refresh();}});window.addEventListener('pagehide',()=>{stopped=true;controller.abort();clearTimeout(transferTimer);clearTimeout(timer);clearTimeout(previewTimer);if(previewBlob)URL.revokeObjectURL(previewBlob);});new ResizeObserver(resize).observe(document.body);
  window.addEventListener('online',()=>{if(!busy&&selectedFile&&transfer?.phase==='Interrupted'&&transfer.retryable)upload(selectedFile);});
  refresh();
})();
