/* Small binary chunks, one upload loop, account-scoped durable backend state. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),CHUNK=4*1024*1024,labels={DRAFT:'Upload to Draft',LIVE:'Upload to Live',UPDATE:'Update Existing'};
  let row=null,manual=false,enabled=true,busy=false,timer=null,previewTimer=null,previewAttempts=0,previewKey='',previewBlob='',promptText='',copyMode='',copyID='',stopped=false;
  const fail=e=>{$('error').textContent=e.message||String(e);$('error').hidden=false;};
  const clear=()=>{$('error').hidden=true;};
  async function request(path,body,raw){
    const response=await fetch('/api/product-uploads/'+path,{credentials:'same-origin',method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':raw?'application/octet-stream':'application/json'},body:body===undefined?undefined:raw?body:JSON.stringify(body)});
    const value=await response.json();if(!response.ok)throw new Error(response.status===403?'Your session expired or access changed. Sign in again, then return to resume your saved upload.':value.error||'Request failed; retry.');return value;
  }
  const action=(name,extra={})=>request(name,{id:row?.id,mode:$('mode').value,...extra});
  function schedule(){clearTimeout(timer);if(!manual&&row&&!['Cloud Ready','Failed','Uploaded'].includes(row.state)&&!busy&&!document.hidden&&!stopped)timer=setTimeout(refresh,5000);}
  function render(){
    $('drop').hidden=manual||!!row?.basic_validated;$('manual').textContent=manual&&enabled?'Use automatic workflow':'Use manual workflow';$('manual').disabled=!enabled;
    $('mode').disabled=busy||(!manual&&!!row?.product_title);$('choose').disabled=busy;$('new').hidden=!row||busy;
    $('summary').hidden=manual||!row;if(row){$('filename').textContent=row.name;$('stage').textContent=row.state;
      $('progress').value=row.size?100*(row.offset||0)/row.size:0;$('progress').hidden=!!row.basic_validated;
      $('detail').textContent=row.reason||(row.basic_validated?'PSD saved and checked. Companion preparation starts after you link the Shopify product.':`${((row.offset||0)/1048576).toFixed(1)} / ${(row.size/1048576).toFixed(1)} MiB saved. Reselect the same PSD to resume.`);
    }
    $('prompt').hidden=!(manual||row?.basic_validated);$('action-label').textContent=labels[$('mode').value];$('copy').disabled=busy||(!manual&&!!row?.product_title);
    $('return').hidden=manual||!row?.copied;$('upload').disabled=busy||!!row?.product_title;$('upload').textContent=row?.product_title?'Linked':'Upload';$('product').readOnly=!!row?.product_title;
    if(row?.lookup&&!$('product').value)$('product').value=row.lookup;
    $('choices').replaceChildren();for(const p of row?.choices||[]){const b=document.createElement('button');b.textContent=`${p.title} · ${p.status} · ${p.handle} · ${p.id.split('/').pop()}`;b.onclick=()=>link(p.id);$('choices').append(b);}
    $('terminal').hidden=manual||!row?.product_title;$('terminal').textContent=row?.product_title?`Linked to ${row.product_title}`:'';
    $('retry').hidden=manual||row?.state!=='Failed'||!row?.product_title;
    if(previewKey&&previewKey!==row?.preview_url){clearTimeout(previewTimer);previewKey='';previewAttempts=0;if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob='';$('preview').textContent='Preview pending';}
    if(row?.basic_validated&&!row.preview_url)$('preview').textContent=row.state==='Failed'?'Preview unavailable':row.product_title?'Preview waiting':'Preview after linking';
    if(row?.preview_url&&previewKey!==row.preview_url)loadPreview(row.preview_url);
    schedule();resize();
  }
  function resize(){if(parent!==window){const height=Math.ceil(document.body.getBoundingClientRect().height);parent.postMessage({type:'sports-cave-product-upload-height',height},location.origin);}}
  window.addEventListener('message',event=>{if(event.origin===location.origin&&event.source===parent&&event.data?.type==='sports-cave-product-upload-measure')resize();});
  async function refresh(){try{const data=await request('state'+(row?.id?'?id='+encodeURIComponent(row.id):''));enabled=data.enabled;row=data.upload;manual=!enabled||manual;if(row)$('mode').value=row.mode;render();}catch(e){fail(e);clearTimeout(timer);}}
  async function fileHash(file){const hashes=[];for(let at=0;at<file.size;at+=CHUNK){const part=await file.slice(at,at+CHUNK).arrayBuffer();hashes.push(new Uint8Array(await crypto.subtle.digest('SHA-256',part)));}const all=new Uint8Array(hashes.length*32);hashes.forEach((h,i)=>all.set(h,i*32));return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',all))).map(b=>b.toString(16).padStart(2,'0')).join('');}
  async function upload(file){
    if(busy||!file)return;clear();busy=true;clearTimeout(timer);
    try{
      if(!/\.psd$/i.test(file.name)||file.size<40||file.size>1073741824)throw new Error('Choose a layered PSD up to 1 GiB.');
      if(row?.basic_validated)throw new Error('Use Start another upload before selecting a different PSD. Your saved upload is retained.');
      const id=row?.id||crypto.randomUUID();$('summary').hidden=false;$('filename').textContent=file.name;$('stage').textContent='Checking file identity';$('progress').value=0;$('progress').hidden=false;$('detail').textContent='Reading bounded chunks to identify this exact PSD.';$('choose').disabled=true;resize();
      const hash=await fileHash(file);
      row=(await request('start',{id,mode:$('mode').value,name:file.name,size:file.size,content_hash:hash})).upload;render();
      while(row.offset<file.size){const offset=row.offset,chunk=file.slice(offset,Math.min(file.size,offset+CHUNK));let result;
        for(let attempt=0;attempt<3;attempt++){try{result=await request(`chunk?id=${encodeURIComponent(id)}&offset=${offset}`,chunk,true);break;}catch(e){if(attempt===2)throw e;await new Promise(r=>setTimeout(r,750*(attempt+1)));}}
        row=result.upload;render();
      }
      row=(await action('finish')).upload;
    }catch(e){fail(e);}finally{busy=false;render();$('file').value='';}
  }
  async function copied(){
    if(copyMode!==$('mode').value||copyID!==(manual?'':row?.id))throw new Error('The selected action changed. Copy the current prompt again.');
    if(!manual)row=(await action('copied')).upload;$('copy').textContent='Copied';$('fallback').close();render();setTimeout(()=>{$('copy').textContent='Copy Prompt';},2200);
  }
  async function copy(){if(busy)return;busy=true;clear();render();$('copy').textContent='Preparing prompt…';try{promptText=(await action('prompt',{id:manual?null:row?.id})).prompt;copyMode=$('mode').value;copyID=manual?'':row?.id;let deadline;try{await Promise.race([navigator.clipboard.writeText(promptText),new Promise((_,reject)=>{deadline=setTimeout(()=>reject(new Error('Clipboard request timed out.')),2500);})]);}catch(e){$('fallback-text').value=promptText;$('fallback').showModal();$('fallback-text').select();fail(new Error('Clipboard access was blocked or did not respond. Use the copy fallback to continue.'));return;}finally{clearTimeout(deadline);}await copied();}catch(e){fail(e);}finally{busy=false;if($('copy').textContent!=='Copied')$('copy').textContent='Copy Prompt';render();}}
  $('fallback-copy').onclick=async()=>{try{$('fallback-text').select();if(!document.execCommand('copy'))throw new Error('Press Ctrl+C while the prompt is selected.');await copied();clear();}catch(e){fail(e);}};
  $('fallback-text').addEventListener('copy',e=>{const t=$('fallback-text');if(e.isTrusted&&t.value.slice(t.selectionStart,t.selectionEnd)===promptText)queueMicrotask(()=>copied().catch(fail));});
  async function link(pid){if(busy)return;busy=true;clear();render();try{row=(await action(pid?'link':'resolve',pid?{product_id:pid}:{value:$('product').value})).upload;
    if(row.product_title){parent.postMessage({type:'sports-cave-product-upload-linked'},location.origin);}
  }catch(e){fail(e);}finally{busy=false;render();}}
  async function loadPreview(url){if(stopped||document.hidden||previewAttempts>=12)return;previewKey=url;previewAttempts++;try{const r=await fetch(url,{credentials:'same-origin'});if(r.status===202){$('preview').textContent='Preparing preview';previewTimer=setTimeout(()=>{if(row?.preview_url===url)loadPreview(url);},5000);return;}if(!r.ok)throw new Error('Preview unavailable');if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob=URL.createObjectURL(await r.blob());if(row?.preview_url!==url)return;const img=new Image();img.alt='Prepared design preview';img.src=previewBlob;$('preview').replaceChildren(img);}catch(e){$('preview').textContent='Preview unavailable';}}
  $('choose').onclick=()=>$('file').click();$('file').onchange=()=>upload($('file').files[0]);$('copy').onclick=copy;$('upload').onclick=()=>link();$('close').onclick=()=>$('fallback').close();
  $('find').onclick=async()=>{clear();try{const f=await action('mockups');parent.location.href='/?page=files&files_path='+encodeURIComponent(f.path);}catch(e){fail(e);}};
  $('mode').onchange=async()=>{clear();try{if(row&&!manual)row=(await action('mode')).upload;$('product').value='';promptText='';render();}catch(e){fail(e);$('mode').value=row.mode;}};
  $('manual').onclick=()=>{manual=!manual;if(!manual&&row)$('mode').value=row.mode;clear();render();};
  $('new').onclick=()=>{row=null;$('product').value='';previewKey='';previewAttempts=0;clearTimeout(previewTimer);$('preview').textContent='Preview pending';clearTimeout(timer);clear();render();};
  $('retry').onclick=async()=>{try{await action('retry');await refresh();}catch(e){fail(e);}};
  for(const event of ['dragenter','dragover'])$('drop').addEventListener(event,e=>{e.preventDefault();$('drop').classList.add('drag');});
  $('drop').addEventListener('dragleave',()=>$('drop').classList.remove('drag'));$('drop').addEventListener('drop',e=>{e.preventDefault();$('drop').classList.remove('drag');upload(e.dataTransfer.files[0]);});
  document.addEventListener('visibilitychange',()=>{clearTimeout(timer);clearTimeout(previewTimer);if(!document.hidden&&!busy){if(row?.preview_url&&!previewBlob){previewKey='';previewAttempts=0;}refresh();}});window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);clearTimeout(previewTimer);if(previewBlob)URL.revokeObjectURL(previewBlob);});new ResizeObserver(resize).observe(document.body);
  refresh();
})();
