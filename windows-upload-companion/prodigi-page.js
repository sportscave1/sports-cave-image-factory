function prodigiExactRow(row,sku,colour) {
  const clean=e=>(e?.innerText||e?.textContent||'').replace(/\s+/g,' ').trim();
  return Array.from(row.querySelectorAll('*')).some(e=>clean(e)===sku) &&
    (!colour||Array.from(row.querySelectorAll('strong')).some(e=>clean(e).toLowerCase()===colour.toLowerCase()));
}
function prodigiPinnedRow(rows,plan) {
  const candidates=Array.from(rows).filter(r=>prodigiExactRow(r,plan.sku,plan.colour)&&
    (!plan.exact_item||r.querySelector('[data-test="line-item-preview-'+plan.item_id+'"]')));
  if(candidates.length>1)throw Error('The exact supplier item is ambiguous.');
  return candidates[0]||null;
}
function prodigiControls(scope,selector) {
  // Prodigi's placement tools are open-shadow web components inside the dialog.
  const found=Array.from(scope.querySelectorAll(selector));
  for(const host of scope.querySelectorAll('*')) {
    if(host.shadowRoot) found.push(...prodigiControls(host.shadowRoot,selector));
  }
  return found;
}
function prodigiProductCard(scope,sku,colour) {
  const found=Array.from(scope.querySelectorAll('button[data-test]')).filter(e=>
    e.getAttribute('data-test')==='select-product-with-data-button-'+sku);
  if(found.length!==1)throw Error('An exact catalogue SKU is required.');
  const select=found[0],card=select.closest('li');
  if(!card)throw Error('Catalogue product card unavailable.');
  const controls=Array.from(card.querySelectorAll('select'));
  if(!colour){if(controls.length)throw Error('Unframed product unexpectedly has options.');return {select};}
  if(controls.length!==1)throw Error('A unique frame colour is required.');
  const options=Array.from(controls[0].options).filter(o=>o.textContent.trim().toLowerCase()===colour.toLowerCase()&&!o.disabled);
  if(options.length!==1)throw Error('The reference frame colour is unavailable.');
  return {select,colour:controls[0],value:options[0].value};
}
async function prodigiFilePicker(getInput,openOptions,findUploadChoice,wait) {
  const existing=getInput();if(existing)return existing;
  await openOptions();
  const choice=await wait(findUploadChoice);choice.click();
  return wait(getInput);
}
async function prodigiReadyProductCard(scope,sku,colour,wait,pin) {
  return wait(()=>{
    pin(); // Identity changes are fatal, never treated as a loading control.
    let current;
    try{current=prodigiProductCard(scope(),sku,colour);}catch{return null;}
    if(current.colour&&current.colour.value!==current.value){
      current.colour.value=current.value;
      current.colour.dispatchEvent(new Event('change',{bubbles:true}));
      return null; // Let React commit, then re-resolve the live card.
    }
    return current.select.disabled?null:current;
  });
}
function prodigiRemovePoint(canvas) {
  // Prodigi draws its trash affordance on a separate, transparent public canvas.
  // Read only that rendered control, never the artwork canvas or application state.
  const w=canvas.width,h=canvas.height,box=canvas.getBoundingClientRect();
  if(!Number.isSafeInteger(w)||!Number.isSafeInteger(h)||w<32||h<32||w*h>8000000||box.width<=0||box.height<=0)
    throw Error('The native remove-image control is unavailable.');
  const pixels=canvas.getContext('2d').getImageData(0,0,w,h).data;
  let x0=w,y0=h,x1=-1,y1=-1,count=0;
  for(let y=0;y<h;y++)for(let x=0;x<w;x++)if(pixels[(y*w+x)*4+3]>20){
    x0=Math.min(x0,x);x1=Math.max(x1,x);y0=Math.min(y0,y);y1=Math.max(y1,y);count++;
  }
  if(count<16||count>60000||x1-x0<4||y1-y0<4||x1-x0>Math.min(256,w/3)||y1-y0>Math.min(256,h/3))
    throw Error('The native remove-image icon cannot be identified safely.');
  return {x:box.left+(x0+x1)/2/w*box.width,y:box.top+(y0+y1)/2/h*box.height};
}
async function prodigiResetControl(getEditor,sku,wait,text,visible) {
  let last='Waiting for '+sku+' and saved image details.';
  try {return await wait(()=>{
    const editor=getEditor();
    if(!editor||!text(editor).includes(sku)||!text(editor).includes('Uploaded image:'))return null;
    const controls=prodigiControls(editor,'canvas[part="remove-canvas"]').filter(visible);
    if(controls.length>1){last='More than one image-removal control is visible.';throw Error(last);}
    if(!controls.length){last='Waiting for the image-removal control to render.';return null;}
    try {return {canvas:controls[0],point:prodigiRemovePoint(controls[0])};}
    catch(error){last=String(error.message||'Native image control unavailable');if(error.name==='SecurityError')throw error;return null;}
  });}catch{throw Error('Reset editor: '+last);}
}
function prodigiIndefiniteHold(scope,text,visible) {
  const saysHeld=/\bpaused indefinitely\b|\bindefinitely paused\b|\bpaused until (?:you )?manually (?:release|resume)\b/i.test(text(scope));
  return saysHeld&&!Array.from(scope.querySelectorAll('h1,h2,h3')).some(e=>visible(e)&&/until production/i.test(text(e)))&&
    !prodigiControls(scope,'button').some(e=>visible(e)&&text(e)==='Pause indefinitely');
}
if(typeof module!=='undefined') module.exports={prodigiExactRow,prodigiPinnedRow,prodigiControls,prodigiFilePicker,prodigiProductCard,prodigiReadyProductCard,prodigiRemovePoint,prodigiResetControl,prodigiIndefiniteHold};
(() => {
  'use strict';
  if(typeof document==='undefined') return;
  const pageInstance=Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
  function reportStage(stage,plan){if(plan?.progress===true)void Promise.resolve(chrome.runtime.sendMessage({type:'prodigi:progress',stage})).catch(()=>{});}
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const visible=e=>e&&e.isConnected&&e.getClientRects().length;
  const text=e=>(e?.innerText||e?.textContent||'').replace(/\s+/g,' ').trim();
  const dialogs=()=>Array.from(document.querySelectorAll('[role="dialog"]')).filter(visible);
  const dialog=name=>dialogs().find(e=>Array.from(e.querySelectorAll('h1,h2')).some(h=>text(h)===name));
  const button=(scope,label)=>{
    const name=e=>e.getAttribute('aria-label')||text(e)||Array.from(e.querySelectorAll('img')).map(i=>i.alt).join(' ');
    const found=prodigiControls(scope,'button').filter(e=>visible(e)&&name(e)===label&&!e.disabled);
    if(found.length!==1) throw Error('A unique '+label+' control is required.');
    return found[0];
  };
  async function wait(check,timeout=120000) {
    if(typeof prodigiObserveReady==='function')return prodigiObserveReady(check,{timeout});
    const end=Date.now()+timeout;
    do {const result=check();if(result)return result;await delay(250);}while(Date.now()<end);
    throw Error('Prodigi did not reach the expected upload state.');
  }
  function locationMatches(plan) {
    const actual=new URL(location.href),pinned=new URL(plan.order_url);
    if(actual.origin!==pinned.origin||actual.pathname!==pinned.pathname||actual.hash||
       actual.username||actual.password||!Array.from(actual.searchParams.keys()).every(
        key=>['imageLibraryType','imageLibraryFileType'].includes(key))) throw Error('The supplier order changed.');
    const sandbox=Array.from(document.querySelectorAll('strong')).some(e=>text(e)==='Sandbox environment');
    if(sandbox!==(plan.environment==='sandbox')) throw Error('Supplier environment differs.');
    if(!Array.from(document.querySelectorAll('h1')).some(e=>text(e).startsWith(plan.order_id)))
      throw Error('The exact supplier order heading is missing.');
    if(!document.querySelector('main')?.textContent.includes(plan.reference)) throw Error('The exact order reference is missing.');
  }
  async function filePickerInput() {
    const picker=await wait(()=>dialog('Select image'));
    return prodigiFilePicker(()=>{
      const inputs=document.querySelectorAll('input[data-test="image-library-upload-from-file-input"][type="file"]');
      return inputs.length===1?inputs[0]:null;
    },()=>button(picker,'Options').click(),()=>{
      const choices=Array.from(document.querySelectorAll('[role="menuitem"]')).filter(e=>visible(e)&&text(e)==='Upload images');
      if(choices.length>1)throw Error('The upload-mode control is ambiguous.');
      return choices[0]||null;
    },wait);
  }
  let running=false;
  async function holdDuplicate(plan) {
    if(running)throw Error('An order operation is already in progress.');
    running=true;let stage='merge-hold';reportStage(stage,plan);
    try {
      locationMatches(plan);
      if(dialogs().length)throw Error('Close the unsaved duplicate editor before its hold.');
      const permission=await chrome.runtime.sendMessage({type:'prodigi:permit',sha256:plan.sha256});
      if(permission?.permitted!==true||permission.order_id!==plan.order_id||permission.operation!=='hold-duplicate')throw Error('The unpaid duplicate changed before its hold.');
      locationMatches(plan);
      const held=()=>prodigiIndefiniteHold(document.querySelector('main'),text,visible);
      if(!held()){
        button(document,'Pause indefinitely').click();
        const state=await wait(()=>held()?true:dialogs()[0]||null);
        if(state!==true){
          if(!/pause/i.test(text(state))||/terms|conditions|agreement/i.test(text(state)))throw Error('The duplicate hold confirmation needs review.');
          const choices=prodigiControls(state,'button').filter(e=>visible(e)&&!e.disabled&&['Pause indefinitely','Pause order','Confirm'].includes(text(e)));
          if(choices.length!==1)throw Error('The duplicate hold confirmation is ambiguous.');
          choices[0].click();
        }
        await wait(held);
      }
      locationMatches(plan);
      return {stage:'merge-hold-confirmed'};
    }catch(error){return {stage,error:String(error.message||'Duplicate hold unconfirmed').slice(0,240)}}
    finally{running=false;}
  }
  async function selectProduct(plan,adding=false) {
    if(running)throw Error('An order operation is already in progress.');
    running=true;let stage='product';reportStage(stage,plan);
    try {
      locationMatches(plan);
      if(dialogs().length)throw Error('An existing editor requires review.');
      if(adding)await wait(()=>{try{return button(document,'Add another item');}catch{return null;}}).then(b=>b.click());
      else {const row=await wait(()=>{
        const choices=Array.from(document.querySelectorAll('button[data-test]')).filter(b=>
          b.getAttribute('data-test')==='choose-product-button-'+plan.item_id&&visible(b)&&text(b)==='Choose product');
        if(choices.length>1)throw Error('The exact blank item is ambiguous.');
        return choices.length===1?choices[0].closest('tr'):null;
      });
      button(row,'Choose product').click();
      }
      stage='product-search';reportStage(stage,plan);
      const picker=await wait(()=>dialog('Select product'));
      // Some Prodigi accounts show the catalogue directly, without tabs.
      const catalogues=prodigiControls(picker,'button').filter(e=>visible(e)&&text(e)==='Catalogue');
      if(catalogues.length>1)throw Error('The catalogue tab is ambiguous.');
      if(catalogues.length===1&&catalogues[0].getAttribute('aria-selected')!=='true')catalogues[0].click();
      const search=await wait(()=>picker.querySelector('input[type="search"]'));
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(search,plan.sku);
      search.dispatchEvent(new Event('input',{bubbles:true}));
      await prodigiReadyProductCard(()=>dialog('Select product'),plan.sku,plan.colour,wait,()=>locationMatches(plan));
      stage='product-select';reportStage(stage,plan);
      locationMatches(plan);
      const permission=await chrome.runtime.sendMessage({type:'prodigi:permit',sha256:plan.sha256});
      if(permission?.permitted!==true)throw Error('The blank item changed before selection.');
      if(adding&&(permission.order_id!==plan.order_id||permission.operation!=='add-item'))throw Error('The Add product permit belongs to another supplier order.');
      locationMatches(plan);
      // Resolve again after React commits the colour; never choose a prefix match/backloader.
      const current=await prodigiReadyProductCard(()=>dialog('Select product'),plan.sku,plan.colour,wait,()=>locationMatches(plan));
      current.select.click();
      stage='product-readback';reportStage(stage,plan);
      if(adding){
        await wait(()=>!dialog('Select product'));
        const editor=dialog('Image Editor');
        if(editor){const close=editor.querySelectorAll('button.col-start-10');if(close.length!==1)throw Error('Close the unsaved new-item editor before upload.');close[0].click();await wait(()=>!dialog('Image Editor'));}
        return {stage}; // The server binds precisely the new empty item by ID.
      }
      await wait(()=>!dialog('Select product')&&Array.from(document.querySelectorAll('table tbody tr')).some(r=>
        r.querySelector('[data-test="line-item-preview-'+plan.item_id+'"]')&&prodigiExactRow(r,plan.sku,plan.colour)));
      return {stage}; // Server independently verifies persistence before any artwork handoff.
    }catch(error){return {stage,error:String(error.message||'Product selection stopped').slice(0,240)};}finally{running=false;}
  }
  async function uploadCertificate(plan) {
    let stage='row';reportStage(stage,plan);
    try {
      const addSlip=await wait(()=>{
        const rows=Array.from(document.querySelectorAll('table tbody tr')).filter(r=>prodigiExactRow(r,plan.sku,plan.colour));
        if(rows.length>1)throw Error('The exact certificate product/frame row is ambiguous.');
        if(rows.length!==1)return null;
        try{return button(document.querySelector('main'),'Add packing slip');}catch{return null;}
      });
      addSlip.click();
      stage='picker';reportStage(stage,plan);
      const input=await filePickerInput();
      stage='transfer';reportStage(stage,plan);
      const parts=[];let received=0;
      while(received<plan.bytes) {
        const answer=await chrome.runtime.sendMessage({type:'prodigi:chunk',offset:received});
        if(!answer?.base64)throw Error('Pinned certificate transfer interrupted.');
        const chunk=Uint8Array.from(atob(answer.base64),c=>c.charCodeAt(0));parts.push(chunk);received+=chunk.length;
      }
      if(received!==plan.bytes)throw Error('Certificate byte count differs.');
      const file=new File(parts,plan.filename,{type:'application/pdf'});
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer())),v=>v.toString(16).padStart(2,'0')).join('');
      if(hash!==plan.sha256)throw Error('Certificate checksum differs.');
      locationMatches(plan);stage='permit';reportStage(stage,plan);
      const permission=await chrome.runtime.sendMessage({type:'prodigi:permit',sha256:hash});
      if(permission?.permitted!==true)throw Error('The draft changed before certificate upload.');
      locationMatches(plan);stage='save';reportStage(stage,plan);
      const transfer=new DataTransfer();transfer.items.add(file);input.files=transfer.files;
      input.dispatchEvent(new Event('change',{bubbles:true}));
      await wait(()=>!dialog('Select image')&&Array.from(document.querySelectorAll('main a')).some(a=>text(a)==='View packing slip'),240000);
      return {saved:true,stage};
    }catch{return {saved:false,stage};}
  }
  async function upload(plan) {
    if(running) throw Error('An upload is already in progress.');
    running=true;
    let stage='page';reportStage(stage,plan);
    try {
      locationMatches(plan);
      if(dialogs().length) throw Error('An existing editor requires manual review.');
      if(plan.kind==='certificate')return await uploadCertificate(plan);
      stage='row';reportStage(stage,plan);
      const row=await wait(()=>{
        const target=prodigiPinnedRow(document.querySelectorAll('table tbody tr'),plan);
        if(!target)return null;
        try {button(target,plan.replace_artwork?'Edit':'Upload');return target;} catch {return null;}
      });
      button(row,plan.replace_artwork?'Edit':'Upload').click();
      stage='editor';reportStage(stage,plan);
      if(plan.replace_artwork){
        stage='reset-image';reportStage(stage,plan);
        const {canvas:remove,point}=await prodigiResetControl(()=>dialog('Image Editor'),plan.sku,wait,text,visible);
        const at={bubbles:true,composed:true,view:window,clientX:point.x,clientY:point.y,button:0};
        remove.dispatchEvent(new PointerEvent('pointerdown',{...at,buttons:1,pointerType:'mouse',isPrimary:true}));
        remove.dispatchEvent(new MouseEvent('mousedown',{...at,buttons:1}));
        remove.dispatchEvent(new PointerEvent('pointerup',{...at,buttons:0,pointerType:'mouse',isPrimary:true}));
        remove.dispatchEvent(new MouseEvent('mouseup',{...at,buttons:0}));
        remove.dispatchEvent(new MouseEvent('click',at));
        // This changes only the unsaved editor. Save is permitted after the
        // replacement file checksum, source and unchanged supplier readback pass.
      }
      const editor=await wait(()=>{
        const e=dialog('Image Editor');if(!e)return null;
        try {button(e,'Add image');return e;} catch {return null;}
      });
      if(!text(editor).includes(plan.sku)) throw Error('Editor product differs.');
      button(editor,'Add image').click();
      stage='picker';reportStage(stage,plan);
      const input=await filePickerInput();
      stage='transfer';reportStage(stage,plan);
      const parts=[];let received=0;
      while(received<plan.bytes) {
        const answer=await chrome.runtime.sendMessage({type:'prodigi:chunk',offset:received});
        if(!answer?.base64) throw Error('Pinned artwork transfer interrupted.');
        const binary=atob(answer.base64);const chunk=Uint8Array.from(binary,c=>c.charCodeAt(0));
        parts.push(chunk);received+=chunk.length;
      }
      if(received!==plan.bytes) throw Error('Pinned artwork byte count differs.');
      const file=new File(parts,plan.filename,{type:'image/jpeg'});
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer())),v=>v.toString(16).padStart(2,'0')).join('');
      if(hash!==plan.sha256) throw Error('Pinned artwork checksum differs.');
      locationMatches(plan);
      const transfer=new DataTransfer();transfer.items.add(file);input.files=transfer.files;
      input.dispatchEvent(new Event('change',{bubbles:true}));
      stage='uploaded';reportStage(stage,plan);
      const loaded=await wait(()=>{
        const e=dialog('Image Editor');return e&&!dialog('Select image')&&text(e).includes('Uploaded image:')&&e;
      },240000);
      const compact=text(loaded).replace(/\s/g,'');
      if(!Array.isArray(plan.dimensions)||!compact.includes(plan.dimensions.join('x')+'px'))
        throw Error('Uploaded image dimensions differ from the numbered archive.');
      const orientation=plan.dimensions[0]>plan.dimensions[1]?'Landscape':'Portrait';
      stage='orientation';reportStage(stage,plan);
      const radios=Array.from(loaded.querySelectorAll('input[type="radio"],[role="radio"]'));
      const target=radios.find(e=>e.getAttribute('aria-label')===orientation||
        (e.labels&&Array.from(e.labels).some(l=>text(l)===orientation))||
        (e.id&&Array.from(loaded.querySelectorAll('label')).some(l=>l.htmlFor===e.id&&text(l)===orientation)));
      if(target && !(target.checked||target.getAttribute('aria-checked')==='true')) target.click();
      await delay(500);
      // Orientation rerenders Prodigi's editor; resolve its current controls.
      const fitted=await wait(()=>{
        const e=dialog('Image Editor');if(!e)return null;
        try {button(e,'fit');return e;} catch {return null;}
      });
      button(fitted,'fit').click();
      await delay(500); // Let the editor commit its orientation/fit state before Save.
      stage='permit';reportStage(stage,plan);
      const permission=await chrome.runtime.sendMessage({type:'prodigi:permit',sha256:hash});
      if(permission?.permitted!==true) throw Error('The draft changed before Save.');
      locationMatches(plan);
      stage='save';reportStage(stage,plan);
      button(dialog('Image Editor'),'Save').click();
      await wait(()=>!dialog('Image Editor'),120000);
      return {saved:true,stage};
    } catch(error) {
      return {saved:false,stage,error:String(error.message||'Artwork preparation stopped').slice(0,240)};
    } finally {running=false;}
  }
  chrome.runtime.onMessage.addListener((message,sender,reply)=>{
    if(sender.id!==chrome.runtime.id) return;
    if(message?.type==='prodigi:ready') {
      const match=location.pathname.match(/^\/orders\/([A-Za-z0-9-]+)\/detail$/);
      reply({page_instance:pageInstance,busy:dialogs().length>0,ready:document.readyState==='complete'&&Boolean(match)&&
        Array.from(document.querySelectorAll('main h1')).some(e=>text(e).startsWith(match[1]))});return;
    }
    if(message?.type==='prodigi:upload') {
      upload(message.plan).then(reply,()=>reply({saved:false}));return true;
    }
    if(message?.type==='prodigi:product') {
      selectProduct(message.plan).then(reply,()=>reply({stage:'product'}));return true;
    }
    if(message?.type==='prodigi:merge-add') {
      selectProduct(message.plan,true).then(reply,()=>reply({stage:'product'}));return true;
    }
    if(message?.type==='prodigi:merge-hold') {
      holdDuplicate(message.plan).then(reply,()=>reply({stage:'merge-hold'}));return true;
    }
  });
})();
