/* Exact Dropbox selection; PSD bytes never pass through this component. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id),labels={DRAFT:'Upload to Draft',LIVE:'Upload to Live',UPDATE:'Update Existing'};
  let row=null,manual=false,enabled=true,busy=false,timer=null,previewTimer=null,previewAttempts=0,previewKey='',previewBlob='',promptText='',copyMode='',copyID='',stopped=false,epoch=0,section='full',isolatedCopy=false,component=false,activeID='',refreshKey='',controller=new AbortController();
  let lastHeight=0,selectedAt=0;const timedReady=new Set();
  const copyFeedbackTimers=new Map(),copyLabels=new Map(['copy'].map(id=>[id,$(id).innerHTML]));
  function restoreCopy(id){clearTimeout(copyFeedbackTimers.get(id));copyFeedbackTimers.delete(id);$(id).innerHTML=copyLabels.get(id);}
  function clearCopyFeedback(){for(const id of copyLabels.keys())restoreCopy(id);}
  function showCopied(id){restoreCopy(id);$(id).textContent='Copied';copyFeedbackTimers.set(id,setTimeout(()=>{restoreCopy(id);resize();},2000));}
  const metrics=window.productUploadMetrics={requests:[],selections:[],note:'Measured browser elapsed time; artwork preparation runs on the server.'};
  function record(list,value){list.push(value);if(list.length>100)list.shift();}
  const abortError=()=>Object.assign(new Error('Selection cancelled'),{name:'AbortError'});
  const notify=()=>{if(component)parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',value:{id:row?.id||null,manual,mode:$('mode').value,visible:!document.hidden,linked:!!row?.product_title,nonce:crypto.randomUUID()},dataType:'json'},'*');};
  function reset(){mapping.clearRecoveryURL?.();mapping.reset();clearCopyFeedback();stopped=false;selectedAt=0;epoch++;controller.abort();controller=new AbortController();row=null;busy=false;promptText='';copyID='';copyMode='';clearTimeout(timer);clearTimeout(previewTimer);previewKey='';previewAttempts=0;if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob='';$('filename').textContent='';$('stage').textContent='';$('detail').textContent='';$('preview').textContent='Preview pending';clear();render();notify();}
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
  let savedRevision='';
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

    const finalReady=!manual&&!!row?.saved_source_version&&section!=='upload';
    $('prompt').hidden=!finalReady||isolatedCopy;$('action-label').textContent=labels[$('mode').value];$('copy').disabled=busy||!finalReady;
    $('return').hidden=!finalReady;mapping.sync(row,finalReady);
    $('terminal').hidden=manual||!row?.product_title||!row?.lifecycle;$('terminal').textContent=row?.product_title?`${row.shopify_completion||'Shopify product verified'} · Linked to ${row.product_title} · ${row.state}${row.reason?' — '+row.reason:''}`:'';
    $('retry').hidden=manual||!row?.lifecycle||row.lifecycle.state!=='Error';$('retry').textContent='Retry file handoff';
    if(previewKey&&previewKey!==row?.preview_url){clearTimeout(previewTimer);previewKey='';previewAttempts=0;if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob='';$('preview').textContent='Preview pending';}
    if(row?.basic_validated&&!row.preview_url)$('preview').textContent=row.state==='Failed'?'Preview unavailable':row.product_title?'Preview waiting':'PSD saved';
    // The final text/mapping component never displays a PSD thumbnail. Loading
    // it here previously repeated Dropbox thumbnail/metadata and cache checks.
    if(section!=='handoff'&&row?.preview_url&&previewKey!==row.preview_url)loadPreview(row.preview_url);
    $('remove').hidden=!row;
    $('artwork-retry').hidden=manual||!row||!['Error','Selected'].includes(row.state);$('artwork-retry').disabled=busy;
    if(section==='upload'){$('prompt').hidden=true;$('return').hidden=true;$('terminal').hidden=true;$('retry').hidden=true;}
    if(section==='handoff'){$('setup').hidden=true;$('automatic').hidden=true;$('footer').hidden=true;$('remove').hidden=true;}
    if(row?.state==='Ready'&&selectedAt&&!timedReady.has(row.id)){timedReady.add(row.id);record(metrics.selections,{id:row.id,selection_to_mockup_ready_ms:Date.now()-selectedAt});}
    schedule();resize();
  }
  function resize(){if(parent!==window){const height=Math.ceil(Math.max(document.body.getBoundingClientRect().height,$('picker').open?Math.min(720,($('picker').scrollHeight||480)+64):0));if(height===lastHeight)return;lastHeight=height;parent.postMessage({type:'sports-cave-product-upload-height',height},location.origin);if(component)parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height},'*');}}
  window.addEventListener('message',event=>{if(event.origin===location.origin&&event.source===parent&&event.data?.type==='sports-cave-product-upload-measure')resize();});
  async function refresh(){const current=epoch,requested=row?.id;try{const data=await request('state'+(row?.id?'?id='+encodeURIComponent(row.id):''));if(current!==epoch||requested!==row?.id)return;const previousManual=manual,previousState=row?.state;if(row?.saved_source_version!==data.upload?.saved_source_version){clearCopyFeedback();}enabled=data.enabled;row=data.upload;manual=!enabled||manual;if(previousManual!==manual||previousState!==row?.state)notify();if(row)$('mode').value=row.mode;render();}catch(e){if(current===epoch&&e.name!=='AbortError')fail(e);clearTimeout(timer);}}
  let pickerRoot='review',pickerPath='',pickerEpoch=0,pickerBusy=false,pickerController=new AbortController(),pickerItems=[];
  const filenameOrder=new Intl.Collator('en',{numeric:true,sensitivity:'accent'});
  let pickerVisible=[],pickerHeights=[],pickerOffsets=[0],pickerFrame=0,pickerWindow='';
  function pickerButton(item,index){const b=document.createElement('button');b.type='button';b.dataset.pickerIndex=index;b.textContent=(item['.tag']==='folder'?'▸ ':'')+item.name;b.onclick=()=>item['.tag']==='folder'?browse(item.path_display):selectPSD(item);return b;}
  function measureOffsets(){pickerOffsets=[0];for(const height of pickerHeights)pickerOffsets.push(pickerOffsets.at(-1)+height);}
  function offsetIndex(position){let lo=0,hi=pickerVisible.length;while(lo<hi){const mid=(lo+hi)>>1;if(pickerOffsets[mid+1]<position)lo=mid+1;else hi=mid;}return lo;}
  function renderPickerWindow(focusIndex=null){
    if(!pickerVisible.length)return;
    const list=$('picker-items'),scroller=$('picker'),virtual=pickerVisible.length>200;list.classList.toggle('picker-virtual',virtual);
    const top=Math.max(0,scroller.getBoundingClientRect().top-list.getBoundingClientRect().top);
    const start=virtual?Math.max(0,(focusIndex??offsetIndex(top))-8):0;
    const end=virtual?Math.min(pickerVisible.length,focusIndex===null?Math.max(start+24,offsetIndex(top+scroller.clientHeight)+8):start+32):pickerVisible.length;
    const key=start+':'+end;if(key===pickerWindow)return;pickerWindow=key;
    const active=list.contains(document.activeElement)?document.activeElement.dataset.pickerIndex:null,fragment=document.createDocumentFragment();
    const spacer=height=>{const div=document.createElement('div');div.style.height=height+'px';div.setAttribute('aria-hidden','true');return div;};
    if(virtual)fragment.append(spacer(pickerOffsets[start]));
    for(let i=start;i<end;i++)fragment.append(pickerButton(pickerVisible[i],i));
    if(virtual)fragment.append(spacer(pickerOffsets.at(-1)-pickerOffsets[end]));
    list.replaceChildren(fragment);
    let changed=false;for(const b of list.querySelectorAll('button')){const i=Number(b.dataset.pickerIndex),height=b.getBoundingClientRect().height+6;if(pickerHeights[i]!==height){pickerHeights[i]=height;changed=true;}}
    if(changed&&virtual){measureOffsets();list.firstChild.style.height=pickerOffsets[start]+'px';list.lastChild.style.height=(pickerOffsets.at(-1)-pickerOffsets[end])+'px';}
    if(active!==null)list.querySelector('[data-picker-index="'+active+'"]')?.focus({preventScroll:true});
  }
  $('picker').addEventListener('scroll',()=>{if(!pickerFrame)pickerFrame=requestAnimationFrame(()=>{pickerFrame=0;renderPickerWindow();});},{passive:true});
  window.addEventListener('resize',()=>{if($('picker').open&&!pickerBusy){pickerWindow='';renderPickerWindow();}});
  $('picker-items').addEventListener('keydown',event=>{
    const b=event.target.closest('button[data-picker-index]');if(!b)return;const i=Number(b.dataset.pickerIndex);
    let next=event.key==='ArrowDown'?i+1:event.key==='ArrowUp'?i-1:event.key==='Home'?0:event.key==='End'?pickerVisible.length-1:event.key==='Tab'?i+(event.shiftKey?-1:1):null;
    if(next===null||next<0||next>=pickerVisible.length)return;event.preventDefault();pickerWindow='';renderPickerWindow(next);
    const target=$('picker-items').querySelector('[data-picker-index="'+next+'"]');target.focus({preventScroll:true});target.scrollIntoView({block:'nearest'});
  });
  function closePicker(){pickerEpoch++;pickerController.abort();pickerBusy=false;clearTimeout($('picker-search').timer);if($('picker').open)$('picker').close();$('choose').focus({preventScroll:true});resize();}
  function breadcrumbs(data){
    const nav=$('picker-path'),base=data.roots[pickerRoot].path;nav.replaceChildren();nav.title=data.path;
    const parts=[pickerRoot==='review'?'Review':'Designs Live',...data.path.slice(base.length).split('/').filter(Boolean)];let target=base;
    parts.forEach((part,index)=>{if(index)target+='/'+part;const path=target,b=document.createElement('button');b.type='button';b.textContent=part;b.disabled=index===parts.length-1;b.onclick=()=>browse(path);nav.append(b);});
  }
  async function renderPicker(){
    const query=$('picker-search').value.toLocaleLowerCase('en');
    pickerVisible=pickerItems.filter(item=>item.name.toLocaleLowerCase('en').includes(query));pickerHeights=pickerVisible.map(()=>44);measureOffsets();pickerWindow='';
    $('picker-items').replaceChildren();$('picker').scrollTop=0;renderPickerWindow();
    $('picker-status').textContent=pickerVisible.length+' of '+pickerItems.length+' PSDs and folders · Complete folder metadata loaded.';
    resize();
  }
  async function browse(path=''){
    pickerController.abort();pickerController=new AbortController();const sequence=++pickerEpoch,root=pickerRoot;
    pickerBusy=true;pickerPath=path;pickerItems=[];pickerVisible=[];$('picker-items').replaceChildren();$('picker-retry').hidden=true;$('picker-items').setAttribute('aria-busy','true');$('picker-status').textContent='Loading Dropbox metadata…';
    const items=new Map(),pages=new Set();let page='',resolvedPath='';
    try{
      do{
        const data=await action('browse',{root,path:resolvedPath||path,page,search:''},pickerController.signal);
        if(sequence!==pickerEpoch)return;
        if(!Array.isArray(data.items)||typeof data.has_more!=='boolean'||(resolvedPath&&data.path!==resolvedPath))throw Error('Folder listing changed. Retry the complete listing.');
        resolvedPath=data.path;pickerPath=data.path;breadcrumbs(data);
        for(const item of data.items){
          const key=item.id||item.path_display?.toLowerCase();
          if(!key||typeof item.name!=='string')throw Error('Folder metadata is incomplete. Retry the complete listing.');
          const previous=items.get(key);
          if(previous&&(previous.rev!==item.rev||previous.path_display!==item.path_display))throw Error('Folder changed while loading. Retry the complete listing.');
          items.set(key,item);
        }
        $('picker-status').textContent='Loading Dropbox metadata… '+items.size+' PSDs and folders found; listing incomplete.';
        page=data.has_more?data.next_page:'';
        if(data.has_more&&(!page||pages.has(page)))throw Error('Folder pagination did not finish. Retry the complete listing.');
        pages.add(page);
      }while(page);
      pickerItems=[...items.values()].sort((a,b)=>filenameOrder.compare(a.name,b.name)||filenameOrder.compare(a.path_display||'',b.path_display||'')||String(a.id||'').localeCompare(String(b.id||'')));
      pickerBusy=false;await renderPicker();
    }catch(e){if(sequence===pickerEpoch&&e.name!=='AbortError'){pickerItems=[];$('picker-items').replaceChildren();$('picker-status').textContent='Could not load the complete folder listing. '+e.message;$('picker-retry').hidden=false;}}
    finally{if(sequence===pickerEpoch){pickerBusy=false;$('picker-items').setAttribute('aria-busy','false');}resize();}
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
  $('picker-search').oninput=()=>{clearTimeout($('picker-search').timer);$('picker-search').timer=setTimeout(()=>{if(!pickerBusy)renderPicker();},150);};
  $('picker-retry').onclick=()=>browse(pickerPath);
  async function copied(version,id='copy'){
    const current=epoch;
    if(copyMode!==$('mode').value||copyID!==(manual?'':row?.id))throw new Error('The selected action changed. Copy the current prompt again.');
    if(!manual)row=(await action('copied',{source_version:version})).upload;if(current!==epoch||stopped)return;render();
  }
  async function copy(){
    if(busy||manual||!row?.saved_source_version)return;restoreCopy('copy');const current=epoch,mode=$('mode').value,id=row.id,version=row.saved_source_version;
    let clipboardWritten=false;busy=true;clear();render();$('copy').textContent='Copying…';
    const valid=()=>{if(current!==epoch||stopped||mode!==$('mode').value||id!==row?.id||version!==row?.saved_source_version)throw abortError();};
    try{
      const text=action('prompt',{id,source_version:version}).then(data=>{valid();return data.prompt;});
      text.catch(()=>{}); // A blocked clipboard must still consume a failed retrieval.
      if(navigator.clipboard?.write&&typeof ClipboardItem==='function'){
        const payload=text.then(value=>new Blob([value],{type:'text/plain'}));payload.catch(()=>{});
        await navigator.clipboard.write([new ClipboardItem({'text/plain':payload})]);
      }else{
        const value=await text;valid();
        if(!navigator.clipboard?.writeText)throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(value);
      }
      valid();clipboardWritten=true;showCopied('copy');copyMode=mode;copyID=id;await copied(version);
    }catch(e){if(current===epoch&&e.name!=='AbortError')fail(new Error((clipboardWritten?'Prompt copied, but its saved status could not be recorded. ':'Could not copy prompt. ')+(e.message||'Allow clipboard access and retry.')));}
    finally{if(current===epoch){busy=false;if($('copy').textContent!=='Copied')restoreCopy('copy');render();}}
  }
  async function loadPreview(url){const current=epoch;if(stopped||document.hidden||previewAttempts>=12)return;previewKey=url;previewAttempts++;try{const r=await fetch(url,{credentials:'same-origin'});if(current!==epoch)return;if(r.status===202){$('preview').textContent='Preparing preview';previewTimer=setTimeout(()=>{if(row?.preview_url===url)loadPreview(url);},5000);return;}if(!r.ok)throw new Error('Preview unavailable');const blob=await r.blob();if(current!==epoch||row?.preview_url!==url)return;if(previewBlob)URL.revokeObjectURL(previewBlob);previewBlob=URL.createObjectURL(blob);const img=new Image();img.alt='Prepared design preview';img.src=previewBlob;img.onload=()=>{if(current===epoch&&selectedAt)record(metrics.selections,{id:row.id,selection_to_preview_ms:Date.now()-selectedAt,representation:url.includes("&prepared=")?"prepared-artwork":"dropbox-thumbnail"});};$('preview').replaceChildren(img);}catch(e){if(current===epoch)$('preview').textContent='Preview unavailable';}}
  $('choose').onclick=()=>{$('picker').showModal();browse();};$('copy').onclick=copy;
  $('mode').onchange=async()=>{clearCopyFeedback();clear();try{if(row&&!manual)row=(await action('mode')).upload;promptText='';render();notify();}catch(e){fail(e);if(row)$('mode').value=row.mode;}};
  $('manual').onclick=()=>{clearCopyFeedback();manual=!manual;if(!manual&&row)$('mode').value=row.mode;clear();render();notify();};
  $('new').onclick=()=>{pickerRoot='review';pickerPath='';$('picker-root').value='review';$('picker-search').value='';reset();};$('remove').onclick=()=>{reset();};
  $('retry').onclick=async()=>{try{await action('retry-file');await refresh();}catch(e){fail(e);}};
  window.addEventListener('pageshow',event=>{if(event.persisted)reset();});
  window.addEventListener('message',event=>{if(event.source!==parent||event.data?.type!=='streamlit:render')return;if(!component)lastHeight=0;component=true;const args=event.data.args||{};section=args.section||'full';isolatedCopy=!!args.isolated_copy;if(section==='handoff'&&savedRevision!==(args.source_version||'')){epoch++;controller.abort();controller=new AbortController();clearCopyFeedback();busy=false;if(row)delete row.saved_source_version;}savedRevision=args.source_version||'';if(section==='upload'&&args.refresh&&args.refresh!==refreshKey){refreshKey=args.refresh;if(row&&!busy)refresh();}if(section==='handoff'&&args.manual){manual=true;if(args.mode)$('mode').value=args.mode;}if(args.id&&(activeID!==args.id||args.mode&&row?.mode!==args.mode||section==='handoff'&&(row?.saved_source_version||'')!==(args.source_version||''))){mapping.reset();epoch++;clearCopyFeedback();controller.abort();controller=new AbortController();activeID=args.id;row={id:args.id};refresh();}render();});
  parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');
  document.addEventListener('visibilitychange',()=>{clearTimeout(timer);clearTimeout(previewTimer);if(section==='upload'&&!busy)notify();if(!document.hidden&&!busy){if(row?.preview_url&&!previewBlob){previewKey='';previewAttempts=0;}refresh();}});window.addEventListener('pagehide',()=>{mapping.dispose();stopped=true;epoch++;clearCopyFeedback();controller.abort();clearTimeout(timer);clearTimeout(previewTimer);if(previewBlob)URL.revokeObjectURL(previewBlob);});try{const frame=window.frameElement;if(frame){const observer=new MutationObserver(()=>{if(!frame.isConnected){stopped=true;epoch++;controller.abort();clearCopyFeedback();clearTimeout(timer);clearTimeout(previewTimer);observer.disconnect();}});observer.observe(window.parent.document,{childList:true,subtree:true});}}catch{}
  new ResizeObserver(resize).observe(document.body);
  refresh();
})();
