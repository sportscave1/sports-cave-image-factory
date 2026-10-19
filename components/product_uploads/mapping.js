/* Mapping owns only its panel/dialog. It never notifies Streamlit or reloads the upload. */
'use strict';
window.ProductUploadMapping = ({request, getRow}) => {
  const $ = id => document.getElementById(id);
  let key='', serial=0, value=null, dialog=null, pending=false, disposed=false;
  let requests=new AbortController(), retryTimer=null, refreshSequence=0, returnFocus=null;
  const colours={'Unmapped':'#ad2929','Mapped':'#197341','Mapping…':'#876614','Pending sync':'#876614','Mapping failed':'#ad2929'};
  const valid=(id,version)=>!disposed && key===id && serial===version && getRow()?.id===id;
  function paint(){
    const state=value?.state||'Checking…';
    $('mapping-status').textContent=(state==='Mapped'?'✓ ':state==='Unmapped'?'● ':'')+state;
    $('mapping-status').style.color=colours[state]||'#62676e';
    $('mapping-reason').textContent=state==='Mapped'?'':value?.reason||'';
    $('map').disabled=!key||pending;
    $('mapping-refresh').disabled=!key||pending;
    if(!dialog)return;
    const d=id=>dialog.querySelector('[data-field="'+id+'"]');
    const product=value?.product;
    d('title').textContent=product?.title||'Find the product created from this upload';
    d('image').hidden=!product?.thumbnail;
    if(product?.thumbnail)d('image').src=product.thumbnail;
    d('psd').textContent=value?.psd||getRow()?.name||'';
    d('state').textContent=state;d('reason').textContent=value?.reason||'';
    d('edition').textContent=value?.edition_limit?`Edition limit ${value.edition_limit} · Next ${value.next_edition||'—'}`:'Edition limit not yet confirmed';
    d('worker').textContent='Worker: '+(value?.worker||'Not registered');
    d('limit-row').hidden=!value?.needs_limit;
    d('retry').hidden=state==='Mapped';d('retry').disabled=pending;
    d('retry').textContent=pending?'Mapping…':'Retry mapping';
    d('legacy').hidden=!!product || pending;
    for(const button of dialog.querySelectorAll('[data-choice]'))button.disabled=pending;
  }
  async function refresh(){
    if(!key||pending)return;
    const id=key,version=serial,sequence=++refreshSequence;
    value={...value,state:'Checking…',reason:''};paint();
    try{
      const result=await request('mapping-status?id='+encodeURIComponent(id),undefined,requests.signal);
      if(valid(id,version)&&sequence===refreshSequence){value=result.mapping;paint();}
    }catch(e){if(valid(id,version)&&e.name!=='AbortError'){value={state:'Status unavailable',reason:e.message};paint();}}
  }
  function close(){
    clearTimeout(retryTimer);retryTimer=null;
    const old=dialog;dialog=null;
    if(old){if(old.open)old.close();old.remove();}
    // Native dialog owns its backdrop; no body styles or permanent scroll locks.
    if(returnFocus?.isConnected)returnFocus.focus({preventScroll:true});returnFocus=null;
  }
  async function map(extra={},attempt=0){
    if(!key||pending)return;
    clearTimeout(retryTimer);retryTimer=null;
    const id=key,version=serial;++refreshSequence;pending=true;
    value={...value,state:'Mapping…',reason:'Refreshing Shopify and verifying this upload…'};paint();
    try{
      const result=await request('map',{id,...extra},requests.signal);
      if(!valid(id,version))return;
      value=result.mapping;
      // Bounded catalogue propagation retry. Never retry a selected/registered
      // product automatically, and stop scheduling as soon as the dialog closes.
      if(dialog && value.state==='Pending sync' && !value.product && !value.needs_limit && attempt<2){
        value.reason+=' Checking again shortly…';
        retryTimer=setTimeout(()=>{if(dialog&&valid(id,version))map({},attempt+1);},2000*(attempt+1));
      }
    }catch(e){if(valid(id,version)&&e.name!=='AbortError')value={...value,state:'Status unavailable',reason:e.message};}
    finally{if(valid(id,version)){
      pending=false;paint();
      if(dialog&&value?.state==='Pending sync'&&!value.product&&!value.needs_limit&&attempt>=2){
        dialog.querySelector('[data-field="legacy"]').open=true;
        choices();
      }
    }}
  }
  async function choices(){
    if(!dialog||pending)return;
    const owner=dialog,id=key,version=serial;
    const list=owner.querySelector('[data-field="choices"]');list.textContent='Checking catalogue…';
    try{
      const result=await request('mapping-candidates',{id,search:owner.querySelector('[data-field="search"]').value},requests.signal);
      if(!valid(id,version)||dialog!==owner)return;
      list.replaceChildren();
      if(!result.choices.length)list.textContent='No candidates found. Search by title or the exact Shopify product ID.';
      for(const product of result.choices){
        const button=owner.ownerDocument.createElement('button');button.type='button';button.dataset.choice=product.id;
        if(product.thumbnail){const img=owner.ownerDocument.createElement('img');img.src=product.thumbnail;img.alt='';button.append(img);}
        const text=owner.ownerDocument.createElement('span');text.textContent=`${product.title} · ${product.status}\n${product.id}`;button.append(text);
        button.onclick=()=>map({product_id:product.id});list.append(button);
      }
    }catch(e){if(valid(id,version)&&dialog===owner&&e.name!=='AbortError')list.textContent=e.message;}
  }
  function open(){
    if(!key||dialog)return;
    // The handoff lives in a small Streamlit iframe. Put the native dialog in
    // its same-origin host so it uses the viewport without enlarging the iframe.
    let doc=document;try{if(parent.document)doc=parent.document;}catch{}
    returnFocus=$('map');dialog=doc.createElement('dialog');
    dialog.className='sc-upload-edition-dialog';dialog.setAttribute('aria-label','Edition Ops mapping');
    dialog.innerHTML=`<style>
      .sc-upload-edition-dialog{box-sizing:border-box;width:540px;max-width:calc(100vw - 32px);max-height:calc(100dvh - 48px);overflow:auto;margin:auto;padding:18px;border:1px solid #d5d2c9;border-radius:8px;background:#fffdf9;color:#252930;font:14px/1.4 "Segoe UI",system-ui,sans-serif;}
      .sc-upload-edition-dialog::backdrop{background:rgba(20,20,18,.28)}
      .sc-upload-edition-dialog *{box-sizing:border-box;min-width:0}.sc-upload-edition-dialog [hidden]{display:none!important}
      .sc-upload-edition-dialog h2{font-size:18px;margin:0 0 12px}.sc-upload-edition-dialog p{margin:7px 0;overflow-wrap:anywhere}
      .sc-upload-edition-dialog .sc-edition-product{display:flex;align-items:center;gap:12px}.sc-upload-edition-dialog img{width:64px;height:64px;object-fit:contain;flex-shrink:0}
      .sc-upload-edition-dialog button,.sc-upload-edition-dialog input{font:inherit;min-height:34px;padding:6px 10px;border:1px solid #d4d7db;border-radius:5px;background:white;color:inherit}
      .sc-upload-edition-dialog button{cursor:pointer}.sc-upload-edition-dialog button:disabled{opacity:.5;cursor:default}
      .sc-upload-edition-dialog button:focus-visible,.sc-upload-edition-dialog input:focus-visible{outline:2px solid #aa8439;outline-offset:2px}
      .sc-upload-edition-dialog input{width:100%;margin:7px 0}.sc-upload-edition-dialog .sc-edition-actions{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end;margin-top:16px}
      .sc-upload-edition-dialog [data-field=choices]{display:grid;gap:8px;margin-top:10px}.sc-upload-edition-dialog [data-choice]{display:flex;gap:10px;text-align:left;align-items:center;white-space:pre-line;overflow-wrap:anywhere}
      .sc-upload-edition-dialog [data-field=retry]{background:#b08b40;border-color:#b08b40;color:white}
    </style><h2>Edition Ops</h2><div class="sc-edition-product"><img data-field="image" alt="Product thumbnail" hidden><strong data-field="title"></strong></div>
    <p>PSD: <span data-field="psd"></span></p><p data-field="edition"></p><strong data-field="state" role="status" aria-live="polite"></strong><p data-field="reason"></p><p data-field="worker"></p>
    <label data-field="limit-row" hidden>Confirmed edition limit<input data-field="limit" type="number" min="1" max="1000" step="1" placeholder="Limit shown on the product"></label>
    <details data-field="legacy"><summary>Select an existing product (legacy upload)</summary><p>Choose only the product created from this upload. Titles are suggestions, not proof of a match.</p><label>Find product<input data-field="search" type="search" placeholder="Title or Shopify product ID"></label><button data-field="find" type="button">Find products</button><div data-field="choices"></div></details>
    <div class="sc-edition-actions"><button data-field="retry" type="button">Retry mapping</button><button data-field="close" type="button" autofocus>Close</button></div>`;
    doc.body.append(dialog);
    dialog.querySelector('[data-field="close"]').onclick=close;
    dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
    dialog.querySelector('[data-field="find"]').onclick=choices;
    dialog.querySelector('[data-field="retry"]').onclick=()=>{
      const input=dialog.querySelector('[data-field="limit"]');
      if(value?.needs_limit&&(!input.value||!input.reportValidity()))return;
      map(value?.needs_limit?{edition_limit:Number(input.value)}:{});
    };
    paint();dialog.showModal();map();
  }
  function reset(){close();serial++;refreshSequence++;requests.abort();requests=new AbortController();pending=false;key='';value=null;paint();}
  const frame=window.frameElement;
  const observer=new MutationObserver(()=>{if(frame&&!frame.isConnected)dispose();});
  try{if(parent!==window)observer.observe(parent.document.body,{childList:true,subtree:true});}catch{}
  function dispose(){if(disposed)return;reset();disposed=true;observer.disconnect();}
  $('map').onclick=open;$('mapping-refresh').onclick=refresh;
  return {reset,dispose,sync(row,visible){
    if(row?.id!==key){reset();key=row?.id||'';}
    if(visible&&key&&!value)refresh();
    if(!visible&&dialog)close();
    paint();
  }};
};
