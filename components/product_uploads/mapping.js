/* Only explicit Map product starts work. Closing the popup does not cancel it. */
'use strict';
window.ProductUploadMapping = ({request, getRow}) => {
  const $ = id => document.getElementById(id);
  const steps=['Finding product','Linking PSD'];
  const stageLabel=s=>s==='Finding Shopify product'?'Finding product':'Linking PSD';
  let key='',source='',mode='',serial=0,value=null,dialog=null,pending=false,disposed=false,visible=false;
  let announced='';
  let requests=new AbortController(),pollTimer=null,returnFocus=null,sequence=0;
  const valid=(id,version)=>!disposed&&visible&&key===id&&serial===version&&getRow()?.id===id&&getRow()?.saved_source_version===source;
  function recoveryURL(clear=false){
    try{
      const host=parent.location?parent:window,url=new URL(host.location.href);
      if(clear){url.searchParams.delete('upload');url.searchParams.delete('sync_map');}
      else{url.searchParams.set('upload',key);url.searchParams.set('sync_map','1');}
      host.history.replaceState(host.history.state,'',url);
    }catch{} // Cross-origin hosts can still reopen the current mounted dialog.
  }
  function paint(){
    const state=value?.state||'Unmapped',success=state==='Mapped';
    if(success&&announced!==key&&window.location?.origin){
      parent.postMessage({type:'sports-cave-product-upload-linked',product_id:value?.product?.id,run_id:value?.run_id},window.location.origin);announced=key;
    }
    $('mapping-status').textContent=success?'✓ Success — PSD mapped':state;
    $('mapping-status').style.color=success?'#197341':['Mapping…','Waiting for product','Mapping incomplete'].includes(state)?'#876614':state==='Unmapped'?'#62676e':'#ad2929';
    $('mapping-reason').textContent=success?value?.product?.title||'':value?.reason||'';
    $('map').disabled=!visible||!key||pending||state==='Mapping…';
    $('map').textContent=success?'Mapped ✓':state==='Mapping…'?stageLabel(value?.stage):'MAP';
    $('mapping-refresh').disabled=!visible||!key||pending;
    if(!dialog)return;
    const d=id=>dialog.querySelector('[data-field="'+id+'"]');
    d('title').textContent=value?.product?.title||'Product from this upload';
    d('psd').textContent=value?.psd||getRow()?.name||'';
    d('state').textContent=success?'Success — PSD mapped':state;
    d('reason').textContent=success?'':value?.reason||'';
    d('edition').textContent=value?.edition_id?`Edition Ops record ${value.edition_id} · Run ${value.run_id}`:'';
    d('edition-link').hidden=!success;
    d('steps').replaceChildren();
    for(const step of steps){
      const item=dialog.ownerDocument.createElement('li');
      item.textContent=(value?.completed?.includes({'Finding product':'Finding Shopify product','Linking PSD':'Verifying'}[step])?'✓ ':stageLabel(value?.stage)===step?'→ ':'')+step;
      if(stageLabel(value?.stage)===step)item.setAttribute('aria-current','step');
      d('steps').append(item);
    }
    d('limit-row').hidden=!value?.needs_limit;
    d('product-row').hidden=!value?.needs_product;
    const select=d('product-choice');select.replaceChildren();
    for(const product of value?.candidates||[]){const option=dialog.ownerDocument.createElement('option');option.value=product.id;option.textContent=product.title+' · '+product.id;select.append(option);}
    select.hidden=!(value?.candidates||[]).length;
    d('product-id').hidden=(value?.candidates||[]).length>0;
    d('retry').hidden=success;
    d('retry').disabled=pending||state==='Mapping…';
    d('retry').textContent=value?.needs_product&&(value.candidates||[]).length?'Confirm product & map':value?.needs_limit?'Confirm & resume':'Retry';
  }
  function schedule(){
    clearTimeout(pollTimer);pollTimer=null;
    if(visible&&value?.state==='Mapping…')pollTimer=setTimeout(refresh,800);
  }
  async function refresh(){
    if(!key||!visible||pending)return;
    const id=key,version=serial,seq=++sequence;
    try{
      const result=await request('mapping-status?id='+encodeURIComponent(id),undefined,requests.signal);
      if(!valid(id,version)||seq!==sequence)return;
      value=result.mapping;paint();schedule();
    }catch(e){if(valid(id,version)&&seq===sequence&&e.name!=='AbortError'){
      value={...value,state:'Status unavailable',reason:e.message+' Retry to reconcile the saved operation.'};paint();
    }}
  }
  async function map(extra={}){
    if(!key||!visible||pending)return;
    clearTimeout(pollTimer);pollTimer=null;
    const id=key,version=serial;++sequence;pending=true;
    value={...value,state:'Mapping…',reason:'',stage:'Finding Shopify product'};paint();
    try{
      const result=await request('map',{id,source_version:source,...extra},requests.signal);
      if(valid(id,version))value=result.mapping;
    }catch(e){if(valid(id,version)&&e.name!=='AbortError')value={...value,state:'Status unavailable',reason:e.message+' Retry to reconcile the saved operation.'};}
    finally{if(valid(id,version)){pending=false;paint();schedule();}}
  }
  function close(){
    const old=dialog;dialog=null;
    if(old){if(old.open)old.close();old.remove();}
    if(returnFocus?.isConnected)returnFocus.focus({preventScroll:true});returnFocus=null;
  }
  async function open(){
    if(!key||!visible||dialog)return;
    recoveryURL(); // Existing authenticated upload-resume route; metadata only.
    let doc=document;try{if(parent.document)doc=parent.document;}catch{}
    returnFocus=$('map');dialog=doc.createElement('dialog');
    dialog.className='sc-upload-edition-dialog';dialog.setAttribute('aria-label','Map product');
    dialog.innerHTML=`<style>
      .sc-upload-edition-dialog{box-sizing:border-box;width:500px;max-width:calc(100vw - 32px);max-height:calc(100dvh - 48px);overflow:auto;margin:auto;padding:18px;border:1px solid #d5d2c9;border-radius:8px;background:#fffdf9;color:#252930;font:14px/1.4 "Segoe UI",system-ui,sans-serif}
      .sc-upload-edition-dialog::backdrop{background:rgba(20,20,18,.28)}
      .sc-upload-edition-dialog *{box-sizing:border-box;min-width:0}.sc-upload-edition-dialog [hidden]{display:none!important}
      .sc-upload-edition-dialog h2{font-size:18px;margin:0 0 12px}.sc-upload-edition-dialog p{margin:7px 0;overflow-wrap:anywhere}
      .sc-upload-edition-dialog ol{line-height:1.8;padding-left:24px}.sc-upload-edition-dialog [aria-current=step]{font-weight:600}
      .sc-upload-edition-dialog button,.sc-upload-edition-dialog input{font:inherit;min-height:34px;padding:6px 10px;border:1px solid #d4d7db;border-radius:5px;background:white;color:inherit}
      .sc-upload-edition-dialog button{cursor:pointer}.sc-upload-edition-dialog button:disabled{opacity:.5;cursor:default}
      .sc-upload-edition-dialog button:focus-visible,.sc-upload-edition-dialog input:focus-visible{outline:2px solid #aa8439;outline-offset:2px}
      .sc-upload-edition-dialog input{width:100%;margin:7px 0}.sc-upload-edition-dialog .sc-edition-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:16px}
      .sc-upload-edition-dialog [data-field=retry]{background:#b08b40;border-color:#b08b40;color:white}
    </style><h2>Map product</h2><strong data-field="title"></strong>
    <ol data-field="steps"></ol><p>PSD: <span data-field="psd"></span></p><p data-field="edition"></p><p><a data-field="edition-link" href="?page=edition_ops" target="_top" hidden>Open Edition Ops</a></p>
    <strong data-field="state" role="status" aria-live="polite"></strong><p data-field="reason"></p>
    <label data-field="limit-row" hidden>Confirmed edition limit<input data-field="limit" type="number" min="1" max="1000" step="1" placeholder="Confirmed product edition limit"></label>
    <label data-field="product-row" hidden>Confirm Shopify product<select data-field="product-choice"></select><input data-field="product-id" placeholder="Shopify product ID from publication" aria-label="Shopify product ID"></label><div class="sc-edition-actions"><button data-field="retry" type="button">Retry</button><button data-field="close" type="button" autofocus>Close</button></div>`;
    doc.body.append(dialog);
    dialog.querySelector('[data-field="close"]').onclick=close;
    dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
    dialog.querySelector('[data-field="retry"]').onclick=()=>{
      const input=dialog.querySelector('[data-field="limit"]');
      if(value?.needs_limit&&(!input.value||!input.reportValidity()))return;
      const extra=value?.needs_limit?{edition_limit:Number(input.value)}:{};
      if(value?.needs_product){
        const chosen=(value.candidates||[]).length?dialog.querySelector('[data-field="product-choice"]').value:dialog.querySelector('[data-field="product-id"]').value.trim();
        if(chosen){extra.product_id=/^\d+$/.test(chosen)?'gid://shopify/Product/'+chosen:chosen;extra.confirm_product=true;}
        else if((value.candidates||[]).length)return;
      }
      map(extra);
    };
    paint();dialog.showModal();
    const owner=dialog,id=key,version=serial;
    await refresh();
    if(valid(id,version)&&dialog===owner&&value?.state==='Unmapped')map();
  }
  function reset(){close();serial++;sequence++;clearTimeout(pollTimer);pollTimer=null;requests.abort();requests=new AbortController();pending=false;key='';source='';mode='';value=null;paint();}
  const frame=window.frameElement;
  const observer=new MutationObserver(()=>{if(frame&&!frame.isConnected)dispose();});
  try{if(parent!==window)observer.observe(parent.document.body,{childList:true,subtree:true});}catch{}
  function dispose(){if(disposed)return;reset();disposed=true;observer.disconnect();}
  $('map').onclick=open;$('mapping-refresh').onclick=refresh;
  return {reset,dispose,clearRecoveryURL:()=>recoveryURL(true),sync(row,enabled){
    if(row?.id!==key||row?.saved_source_version!==source||row?.mode!==mode||!enabled&&visible){
      reset();key=row?.id||'';source=row?.saved_source_version||'';mode=row?.mode||'';
    }
    visible=!!enabled&&!!source;
    if(!visible&&dialog)close();
    // No lookups, catalogue calls or scans when the component mounts.
    paint();
  }};
};
