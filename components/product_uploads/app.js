/* Exact Dropbox selection; PSD bytes never pass through this component. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),labels={DRAFT:'Upload to Draft',LIVE:'Upload to Live',UPDATE:'Update Existing'};
  let row=null,manual=false,enabled=true,busy=false,timer=null,previewTimer=null,previewAttempts=0,previewKey='',previewBlob='',promptText='',copyMode='',copyID='',stopped=false,epoch=0,section='full',component=false,activeID='',refreshKey='',controller=new AbortController();
  let lastHeight=0,selectedAt=0;const timedReady=new Set();
  const copyFeedbackTimers=new Map(),copyLabels=new Map(['copy','fallback-copy'].map(id=>[id,$(id).innerHTML]));
  function restoreCopy(id){clearTimeout(copyFeedbackTimers.get(id));copyFeedbackTimers.delete(id);$(id).innerHTML=copyLabels.get(id);}
  function clearCopyFeedback(){for(const id of copyLabels.keys())restoreCopy(id);}
  function showCopied(id){restoreCopy(id);$(id).textContent='Copied';copyFeedbackTimers.set(id,setTimeout(()=>{restoreCopy(id);resize();},2000));}
  const metrics=window.productUploadMetrics={requests:[],selections:[],note:'Measured browser elapsed time; artwork preparation runs on the server.'};
  function record(list,value){list.push(value);if(list.length>100)list.shift();}
  const abortError=()=>Object.assign(new Error('Selection cancelled'),{name:'AbortError'});
  const notify=()=>{if(component)parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',value:{id:row?.id||null,manual,mode:$('mode').value,visible:!document.hidden,linked:!!row?.product_title,nonce:crypto.randomUUID()},dataType:'json'},'*');};
  function reset(){savedPackage.reset();mapping.reset();clearCopyFeedback();stopped=false;selectedAt=0;epoch++;controller.abort();controller=new AbortController();row=null;busy=false;promptText='';copyID='';copyMode='';clearTimeout(timer);clearTimeout(previewTimer);previewKey='';previewAttempts=0;if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob='';$('filename').textContent='';$('stage').textContent='';$('detail').textContent='';$('preview').textContent='Preview pending';$('fallback').close();clear();render();notify();}
  const fail=e=>{if(e.name==='AbortError')return;$('error').textContent=e.message||String(e);$('error').hidden=false;};
  const clear=()=>{$('error').hidden=true;};
  async function request(path,body,signal=controller.signal){
    const generation=epoch,started=Date.now();
    const response=await fetch('/api/product-uploads/'+path,{method:body?'POST':'GET',credentials:'same-origin',signal,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
    const data=await response.json();if(generation!==epoch)throw abortError();
    record(metrics.requests,{operation:path.split('?')[0],elapsed_ms:Date.now()-started,status:response.status});
    if(!response.ok)throw Object.assign(new Error(data.error||'Dropbox request failed. Retry.'),{upload:data.upload});return data;
  }
  const action=(name,extra={},signal)=>request(name,{id:row?.id,mode:$('mode').value,...extra},signal);
  const mapping=window.ProductUploadMapping({request,getRow:()=>row});
  const savedPackage=window.ProductUploadPackage({request,resize});let savedRevision='';
  function schedule(){clearTimeout(timer);if(!manual&&row?.basic_validated&&!['Ready','Cloud Ready','Failed','Uploaded','Error','Shopify confirmed'].includes(row.state)&&!busy&&!document.hidden&&!stopped)timer=setTimeout(refresh,row.state==='Preparing'?750:1000);}
  function render(){
    $('drop').hidden=manual;$('manual').textContent=manual&&enabled?'Use automatic workflow':'Use manual workflow';$('manual').disabled=!enabled||busy;
    $('mode').disabled=busy;$('choose').disabled=busy;$('new').hidden=!row||busy;
    $('summary').hidden=manual||!row;if(row){$('filename').textContent=row.name;$('stage').textContent=row.state==='Checking design'?'Processing':row.state;
      const preparation=row.artwork_progress,bar=$('progress');bar.hidden=false;bar.setAttribute('aria-label','PSD preparation progress');
      if(row.state==='Ready'){bar.value=100;$('stage').textContent='Ready';}
      else if(preparation?.stage==='Downloading PSD'&&preparation.total){bar.value=100*preparation.completed/preparation.total;$('stage').textContent=`Downloading PSD · ${(preparation.completed/1048576).toFixed(1)} / ${(preparation.total/1048576).toFixed(1)} MiB · ${Math.floor(bar.value)}%`;}
      else{bar.removeAttribute('value');$('stage').textContent=preparation?.stage||(row.state==='Preparing'?'Waiting to start':row.state);}
      $('detail').textContent=(row.source?`${row.source.path_display} · Revision ${row.source.rev} · `:'')+((row.lifecycle?`${row.lifecycle.state}${row.lifecycle.reason?' · '+row.lifecycle.reason:''}`:row.reason)||'Exact Dropbox PSD selected. Artwork preparation runs on the server.');
    }

    $('prompt').hidden=!(manual||row?.basic_validated);$('action-label').textContent=labels[$('mode').value];$('copy').disabled=busy;
    $('return').hidden=manual||!row?.basic_validated;mapping.sync(row,section!=='upload'&&!manual);savedPackage.sync(row,section!=='upload'&&!manual,savedRevision);
    $('terminal').hidden=manual||!row?.product_title||!row?.lifecycle;$('terminal').textContent=row?.product_title?`${row.shopify_completion||'Shopify product verified'} · Linked to ${row.product_title} · ${row.state}${row.reason?' — '+row.reason:''}`:'';
    $('retry').hidden=manual||!row?.lifecycle||row.lifecycle.state!=='Error';$('retry').textContent='Retry file handoff';
    if(previewKey&&previewKey!==row?.preview_url){clearTimeout(previewTimer);previewKey='';previewAttempts=0;if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob='';$('preview').textContent='Preview pending';}
    if(row?.basic_validated&&!row.preview_url)$('preview').textContent=row.state==='Failed'?'Preview unavailable':row.product_title?'Preview waiting':'PSD saved';
    if(row?.preview_url&&previewKey!==row.preview_url)loadPreview(row.preview_url);
    $('remove').hidden=!row;
    $('artwork-retry').hidden=manual||!row||!['Error','Selected'].includes(row.state);$('artwork-retry').disabled=busy;
    if(section==='upload'){$('prompt').hidden=true;$('return').hidden=true;$('terminal').hidden=true;$('retry').hidden=true;}
    if(section==='handoff'){$('setup').hidden=true;$('automatic').hidden=true;$('footer').hidden=true;$('remove').hidden=true;}
    if(row?.state==='Ready'&&selectedAt&&!timedReady.has(row.id)){timedReady.add(row.id);record(metrics.selections,{id:row.id,selection_to_mockup_ready_ms:Date.now()-selectedAt});}
    schedule();resize();
  }
  function resize(){if(parent!==window){const height=Math.ceil(Math.max(document.body.getBoundingClientRect().height,$('picker').open?Math.min(720,($('picker').scrollHeight||480)+64):0));if(height===lastHeight)return;lastHeight=height;parent.postMessage({type:'sports-cave-product-upload-height',height},location.origin);if(component)parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height},'*');}}
  window.addEventListener('message',event=>{if(event.origin===location.origin&&event.source===parent&&event.data?.type==='sports-cave-product-upload-measure')resize();});
  async function refresh(){const current=epoch,requested=row?.id;try{const data=await request('state'+(row?.id?'?id='+encodeURIComponent(row.id):''));if(current!==epoch||requested!==row?.id)return;const previousManual=manual,previousState=row?.state;enabled=data.enabled;row=data.upload;manual=!enabled||manual;if(previousManual!==manual||previousState!==row?.state)notify();if(row)$('mode').value=row.mode;render();}catch(e){if(current===epoch&&e.name!=='AbortError')fail(e);clearTimeout(timer);}}
  let pickerRoot='review',pickerPath='',pickerPage='',pickerEpoch=0,pickerBusy=false,pickerController=new AbortController();
  function closePicker(){pickerEpoch++;pickerController.abort();pickerBusy=false;clearTimeout($('picker-search').timer);if($('picker').open)$('picker').close();$('choose').focus({preventScroll:true});resize();}
  function breadcrumbs(data){
    const nav=$('picker-path'),base=data.roots[pickerRoot].path;nav.replaceChildren();nav.title=data.path;
    const parts=[pickerRoot==='review'?'Review':'Designs Live',...data.path.slice(base.length).split('/').filter(Boolean)];let target=base;
    parts.forEach((part,index)=>{if(index)target+='/'+part;const path=target,b=document.createElement('button');b.type='button';b.textContent=part;b.disabled=index===parts.length-1;b.onclick=()=>browse(path);nav.append(b);});
  }
  async function browse(path='',page=''){
    pickerController.abort();pickerController=new AbortController();const sequence=++pickerEpoch;pickerBusy=true;if(!page)$('picker-items').replaceChildren();$('picker-more').disabled=true;$('picker-status').textContent='Loading Dropbox metadata…';
    try{
      const data=await action('browse',{root:pickerRoot,path,page,search:$('picker-search').value},pickerController.signal);
      if(sequence!==pickerEpoch)return;pickerPath=data.path;pickerPage=data.next_page;
      breadcrumbs(data);$('picker-more').hidden=!data.has_more;
      if(!page)$('picker-items').replaceChildren();
      for(const item of data.items){const b=document.createElement('button');b.textContent=(item['.tag']==='folder'?'▸ ':'')+item.name;
        b.onclick=()=>item['.tag']==='folder'?browse(item.path_display):selectPSD(item);$('picker-items').append(b);}
      $('picker-status').textContent=data.has_more?'More metadata available. Load more to continue this folder search.':'Folder metadata loaded.';
    }catch(e){if(sequence===pickerEpoch&&e.name!=='AbortError')$('picker-status').textContent=e.message;}
    finally{if(sequence===pickerEpoch){pickerBusy=false;$('picker-more').disabled=false;}resize();}
  }
  async function selectPSD(item){
    closePicker();reset();selectedAt=Date.now();const current=epoch;busy=true;row={name:item.name,source:item,size:item.size,state:'Checking selection',basic_validated:false};render();
    try{const selected=await action('select',{id:crypto.randomUUID(),file_id:item.id,revision:item.rev});
      if(current!==epoch)return;row=selected.upload;record(metrics.selections,{id:row.id,selection_to_bound_ms:Date.now()-selectedAt});busy=false;render();notify();row.state='Preparing';render();const prepared=await action('prepare');if(current!==epoch)return;row=prepared.upload;notify();
    }catch(e){if(current===epoch){if(e.upload){row=e.upload;notify();}fail(e);}}finally{if(current===epoch){busy=false;render();}}
  }
  $('picker-close').onclick=closePicker;$('picker').addEventListener('close',resize);
  $('picker').addEventListener('cancel',event=>{event.preventDefault();closePicker();});
  $('artwork-retry').onclick=async()=>{if(busy||!row)return;const current=epoch;busy=true;clear();row.state='Preparing';row.reason='';render();try{const result=await action('prepare');if(current!==epoch)return;row=result.upload;notify();}catch(e){if(current===epoch){if(e.upload)row=e.upload;else await refresh();notify();fail(e);}}finally{if(current===epoch){busy=false;render();}}};
  $('picker-root').onchange=()=>{pickerRoot=$('picker-root').value;$('picker-search').value='';browse();};
  $('picker-search').oninput=()=>{clearTimeout($('picker-search').timer);$('picker-search').timer=setTimeout(()=>browse(pickerPath),250);};
  $('picker-more').onclick=()=>{if(!pickerBusy)browse(pickerPath,pickerPage);};
  async function copied(id='copy'){
    const current=epoch;
    if(copyMode!==$('mode').value||copyID!==(manual?'':row?.id))throw new Error('The selected action changed. Copy the current prompt again.');
    if(!manual)row=(await action('copied')).upload;if(current!==epoch||stopped)return;showCopied(id);$('fallback').close();render();
  }
  async function copy(){if(busy)return;restoreCopy('copy');const current=epoch;busy=true;clear();render();$('copy').textContent='Preparing prompt…';try{promptText=(await action('prompt',{id:manual?null:row?.id})).prompt;if(current!==epoch)return;copyMode=$('mode').value;copyID=manual?'':row?.id;let deadline;try{await Promise.race([navigator.clipboard.writeText(promptText),new Promise((_,reject)=>{deadline=setTimeout(()=>reject(new Error('Clipboard request timed out.')),2500);})]);}catch(e){if(current!==epoch)return;$('fallback-text').value=promptText;$('fallback').showModal();$('fallback-text').select();fail(new Error('Clipboard access was blocked or did not respond. Use the copy fallback to continue.'));return;}finally{clearTimeout(deadline);}if(current!==epoch)return;await copied();}catch(e){fail(e);}finally{if(current!==epoch)return;busy=false;if($('copy').textContent!=='Copied')restoreCopy('copy');render();}}
  $('fallback-copy').onclick=async()=>{restoreCopy('fallback-copy');try{$('fallback-text').select();if(!document.execCommand('copy'))throw new Error('Press Ctrl+C while the prompt is selected.');await copied('fallback-copy');clear();}catch(e){fail(e);}};
  $('fallback-text').addEventListener('copy',e=>{const t=$('fallback-text');if(e.isTrusted&&t.value.slice(t.selectionStart,t.selectionEnd)===promptText)queueMicrotask(()=>copied().catch(fail));});
  async function loadPreview(url){const current=epoch;if(stopped||document.hidden||previewAttempts>=12)return;previewKey=url;previewAttempts++;try{const r=await fetch(url,{credentials:'same-origin'});if(current!==epoch)return;if(r.status===202){$('preview').textContent='Preparing preview';previewTimer=setTimeout(()=>{if(row?.preview_url===url)loadPreview(url);},5000);return;}if(!r.ok)throw new Error('Preview unavailable');const blob=await r.blob();if(current!==epoch||row?.preview_url!==url)return;if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob=URL.createObjectURL(blob);const img=new Image();img.alt='Prepared design preview';img.src=previewBlob;img.onload=()=>{if(current===epoch&&selectedAt)record(metrics.selections,{id:row.id,selection_to_preview_ms:Date.now()-selectedAt,representation:url.includes("&prepared=")?"prepared-artwork":"dropbox-thumbnail"});};$('preview').replaceChildren(img);}catch(e){if(current===epoch)$('preview').textContent='Preview unavailable';}}
  $('choose').onclick=()=>{$('picker').showModal();browse();};$('copy').onclick=copy;$('close').onclick=()=>$('fallback').close();
  $('mode').onchange=async()=>{clear();try{if(row&&!manual)row=(await action('mode')).upload;promptText='';render();notify();}catch(e){fail(e);if(row)$('mode').value=row.mode;}};
  $('manual').onclick=()=>{manual=!manual;if(!manual&&row)$('mode').value=row.mode;clear();render();notify();};
  $('new').onclick=()=>{pickerRoot='review';pickerPath='';pickerPage='';$('picker-root').value='review';$('picker-search').value='';reset();};$('remove').onclick=()=>{reset();};
  $('retry').onclick=async()=>{try{await action('retry-file');await refresh();}catch(e){fail(e);}};
  window.addEventListener('pageshow',event=>{if(event.persisted)reset();});
  window.addEventListener('message',event=>{if(event.source!==parent||event.data?.type!=='streamlit:render')return;if(!component)lastHeight=0;component=true;const args=event.data.args||{};section=args.section||'full';if(savedRevision&&savedRevision!==(args.package_version||'')){epoch++;controller.abort();controller=new AbortController();clearCopyFeedback();busy=false;savedPackage.reset();}savedRevision=args.package_version||'';if(section==='upload'&&args.refresh&&args.refresh!==refreshKey){refreshKey=args.refresh;if(row&&!busy)refresh();}if(section==='handoff'&&args.manual){manual=true;if(args.mode)$('mode').value=args.mode;}if(args.id&&(activeID!==args.id||args.mode&&row?.mode!==args.mode||args.package_version&&row?.saved_package_version!==args.package_version)){savedPackage.reset();mapping.reset();epoch++;clearCopyFeedback();controller.abort();controller=new AbortController();activeID=args.id;row={id:args.id};refresh();}render();});
  parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');
  document.addEventListener('visibilitychange',()=>{clearTimeout(timer);clearTimeout(previewTimer);if(section==='upload'&&!busy)notify();if(!document.hidden&&!busy){if(row?.preview_url&&!previewBlob){previewKey='';previewAttempts=0;}refresh();}});window.addEventListener('pagehide',()=>{savedPackage.dispose();mapping.dispose();stopped=true;epoch++;clearCopyFeedback();controller.abort();clearTimeout(timer);clearTimeout(previewTimer);if(previewBlob)URL.revokeObjectURL(previewBlob);});try{const frame=window.frameElement;if(frame){const observer=new MutationObserver(()=>{if(!frame.isConnected){stopped=true;epoch++;controller.abort();clearCopyFeedback();clearTimeout(timer);clearTimeout(previewTimer);observer.disconnect();}});observer.observe(window.parent.document,{childList:true,subtree:true});}}catch{}
  new ResizeObserver(resize).observe(document.body);
  refresh();
})();
