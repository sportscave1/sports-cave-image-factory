/* Small binary chunks, one upload loop, account-scoped durable backend state. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),CHUNK=4*1024*1024,labels={DRAFT:'Upload to Draft',LIVE:'Upload to Live',UPDATE:'Update Existing'};
  let row=null,manual=false,enabled=true,busy=false,timer=null,previewTimer=null,previewAttempts=0,previewKey='',previewBlob='',promptText='',copyMode='',copyID='',stopped=false,epoch=0,section='full',component=false,activeID='',refreshKey='',controller=new AbortController();
  const notify=()=>{if(component)parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',value:{id:row?.id||null,manual,mode:$('mode').value,visible:!document.hidden,linked:!!row?.product_title,nonce:crypto.randomUUID()},dataType:'json'},'*');};
  function reset(){epoch++;controller.abort();controller=new AbortController();row=null;busy=false;promptText='';copyID='';copyMode='';clearTimeout(timer);clearTimeout(previewTimer);previewKey='';previewAttempts=0;if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob='';$('file').value='';$('product').value='';$('filename').textContent='';$('stage').textContent='';$('detail').textContent='';$('choices').replaceChildren();$('preview').textContent='Preview pending';$('fallback').close();clear();render();notify();}
  const fail=e=>{if(e.name==='AbortError')return;$('error').textContent=e.message||String(e);$('error').hidden=false;};
  const clear=()=>{$('error').hidden=true;};
  async function request(path,body,raw){
    const generation=epoch;const response=await fetch('/api/product-uploads/'+path,{credentials:'same-origin',signal:controller.signal,method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':raw?'application/octet-stream':'application/json'},body:body===undefined?undefined:raw?body:JSON.stringify(body)});
    const value=await response.json();if(generation!==epoch){const stale=new Error('Superseded workflow');stale.name='AbortError';throw stale;}if(!response.ok)throw new Error(response.status===403?'Your session expired or access changed. Sign in again, then return to resume your saved upload.':value.error||'Request failed; retry.');return value;
  }
  const action=(name,extra={})=>request(name,{id:row?.id,mode:$('mode').value,...extra});
  function schedule(){clearTimeout(timer);if(!manual&&row&&!['Cloud Ready','Failed','Uploaded'].includes(row.state)&&!busy&&!document.hidden&&!stopped)timer=setTimeout(refresh,5000);}
  function render(){
    $('drop').hidden=manual||!!row?.basic_validated;$('manual').textContent=manual&&enabled?'Use automatic workflow':'Use manual workflow';$('manual').disabled=!enabled||busy;
    $('mode').disabled=busy;$('choose').disabled=busy;$('new').hidden=!row||busy;
    $('summary').hidden=manual||!row;if(row){$('filename').textContent=row.name;$('stage').textContent=row.state;
      $('progress').value=row.size?100*(row.offset||0)/row.size:0;$('progress').hidden=!!row.basic_validated;
      $('detail').textContent=row.reason||(row.basic_validated?'PSD saved and checked. Generate product images below; edition preparation starts after verified Shopify completion.':`${((row.offset||0)/1048576).toFixed(1)} / ${(row.size/1048576).toFixed(1)} MiB saved. Reselect the same PSD to resume.`);
    }
    $('prompt').hidden=!(manual||row?.basic_validated);$('action-label').textContent=labels[$('mode').value];$('copy').disabled=busy||(!manual&&!!row?.product_title);
    $('return').hidden=manual||!row?.copied;$('upload').disabled=busy||!!row?.product_title;$('upload').textContent=row?.product_title?'Linked':'Upload';$('product').readOnly=!!row?.product_title;
    if(row?.lookup&&!$('product').value)$('product').value=row.lookup;
    $('choices').replaceChildren();for(const p of row?.choices||[]){const b=document.createElement('button');b.textContent=`${p.title} · ${p.status} · ${p.handle} · ${p.id.split('/').pop()}`;b.onclick=()=>link(p.id);$('choices').append(b);}
    $('terminal').hidden=manual||!row?.product_title;$('terminal').textContent=row?.product_title?`${row.shopify_completion||'Shopify product verified'} · Linked to ${row.product_title} · ${row.state}${row.reason?' — '+row.reason:''}`:'';
    $('retry').hidden=manual||row?.state!=='Failed'||!row?.product_title;
    if(previewKey&&previewKey!==row?.preview_url){clearTimeout(previewTimer);previewKey='';previewAttempts=0;if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob='';$('preview').textContent='Preview pending';}
    if(row?.basic_validated&&!row.preview_url)$('preview').textContent=row.state==='Failed'?'Preview unavailable':row.product_title?'Preview waiting':'PSD saved';
    if(row?.preview_url&&previewKey!==row.preview_url)loadPreview(row.preview_url);
    $('remove').hidden=!row;
    if(section==='upload'){$('prompt').hidden=true;$('return').hidden=true;$('terminal').hidden=true;$('retry').hidden=true;}
    if(section==='handoff'){$('setup').hidden=true;$('automatic').hidden=true;$('footer').hidden=true;$('remove').hidden=true;}
    schedule();resize();
  }
  function resize(){if(parent!==window){const height=Math.ceil(document.body.getBoundingClientRect().height);parent.postMessage({type:'sports-cave-product-upload-height',height},location.origin);if(component)parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height},'*');}}
  window.addEventListener('message',event=>{if(event.origin===location.origin&&event.source===parent&&event.data?.type==='sports-cave-product-upload-measure')resize();});
  async function refresh(){const current=epoch,requested=row?.id;try{const data=await request('state'+(row?.id?'?id='+encodeURIComponent(row.id):''));if(current!==epoch||requested!==row?.id)return;const previousManual=manual;enabled=data.enabled;row=data.upload;manual=!enabled||manual;if(previousManual!==manual)notify();if(row)$('mode').value=row.mode;render();}catch(e){if(current===epoch&&e.name!=='AbortError')fail(e);clearTimeout(timer);}}
  async function fileHash(file){const hashes=[];for(let at=0;at<file.size;at+=CHUNK){const part=await file.slice(at,at+CHUNK).arrayBuffer();hashes.push(new Uint8Array(await crypto.subtle.digest('SHA-256',part)));}const all=new Uint8Array(hashes.length*32);hashes.forEach((h,i)=>all.set(h,i*32));return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',all))).map(b=>b.toString(16).padStart(2,'0')).join('');}
  async function upload(file){
    if(busy||!file)return;const current=epoch;clear();busy=true;clearTimeout(timer);
    try{
      if(!/\.psd$/i.test(file.name)||file.size<40||file.size>1073741824)throw new Error('Choose a layered PSD up to 1 GiB.');
      if(row?.basic_validated)throw new Error('Use Start another upload before selecting a different PSD. Your saved upload is retained.');
      const id=row?.id||crypto.randomUUID();$('summary').hidden=false;$('filename').textContent=file.name;$('stage').textContent='Checking file identity';$('progress').value=0;$('progress').hidden=false;$('detail').textContent='Reading bounded chunks to identify this exact PSD.';$('choose').disabled=true;$('remove').hidden=false;resize();
      const hash=await fileHash(file);if(current!==epoch)return;
      const started=await request('start',{id,mode:$('mode').value,name:file.name,size:file.size,content_hash:hash});if(current!==epoch)return;row=started.upload;render();
      while(row.offset<file.size){const offset=row.offset,chunk=file.slice(offset,Math.min(file.size,offset+CHUNK));let result;
        for(let attempt=0;attempt<3;attempt++){try{result=await request(`chunk?id=${encodeURIComponent(id)}&offset=${offset}`,chunk,true);break;}catch(e){if(attempt===2)throw e;await new Promise(r=>setTimeout(r,750*(attempt+1)));}}
        if(current!==epoch)return;row=result.upload;render();
      }
      const finished=await action('finish');if(current!==epoch)return;row=finished.upload;notify();
    }catch(e){if(current===epoch&&e.name!=='AbortError')fail(e);}finally{if(current===epoch){busy=false;render();$('file').value='';}}
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
  $('new').onclick=reset;$('remove').onclick=reset;
  $('retry').onclick=async()=>{try{await action('retry');await refresh();}catch(e){fail(e);}};
  for(const event of ['dragenter','dragover'])$('drop').addEventListener(event,e=>{e.preventDefault();$('drop').classList.add('drag');});
  $('drop').addEventListener('dragleave',()=>$('drop').classList.remove('drag'));$('drop').addEventListener('drop',e=>{e.preventDefault();$('drop').classList.remove('drag');upload(e.dataTransfer.files[0]);});
  window.addEventListener('pageshow',event=>{if(event.persisted)reset();});
  window.addEventListener('message',event=>{if(event.source!==parent||event.data?.type!=='streamlit:render')return;component=true;const args=event.data.args||{};section=args.section||'full';if(section==='upload'&&args.refresh&&args.refresh!==refreshKey){refreshKey=args.refresh;if(row&&!busy)refresh();}if(section==='handoff'&&args.manual){manual=true;if(args.mode)$('mode').value=args.mode;}if(section==='handoff'&&args.id&&(activeID!==args.id||args.mode&&row?.mode!==args.mode)){activeID=args.id;row={id:args.id};refresh();}render();});
  parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');
  document.addEventListener('visibilitychange',()=>{clearTimeout(timer);clearTimeout(previewTimer);if(section==='upload')notify();if(!document.hidden&&!busy){if(row?.preview_url&&!previewBlob){previewKey='';previewAttempts=0;}refresh();}});window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);clearTimeout(previewTimer);if(previewBlob)URL.revokeObjectURL(previewBlob);});new ResizeObserver(resize).observe(document.body);
  refresh();
})();
