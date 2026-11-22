function prodigiExactRow(row,sku,colour) {
  const clean=e=>(e?.innerText||e?.textContent||'').replace(/\s+/g,' ').trim();
  return Array.from(row.querySelectorAll('*')).some(e=>clean(e)===sku) &&
    (!colour||Array.from(row.querySelectorAll('strong')).some(e=>clean(e).toLowerCase()===colour.toLowerCase()));
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
if(typeof module!=='undefined') module.exports={prodigiExactRow,prodigiControls,prodigiFilePicker,prodigiProductCard};
(() => {
  'use strict';
  if(typeof document==='undefined') return;
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
  async function selectProduct(plan) {
    if(running)throw Error('An order operation is already in progress.');
    running=true;let stage='product';
    try {
      locationMatches(plan);
      if(dialogs().length)throw Error('An existing editor requires review.');
      const row=await wait(()=>{
        const choices=Array.from(document.querySelectorAll('button[data-test]')).filter(b=>
          b.getAttribute('data-test')==='choose-product-button-'+plan.item_id&&visible(b)&&text(b)==='Choose product');
        if(choices.length>1)throw Error('The exact blank item is ambiguous.');
        return choices.length===1?choices[0].closest('tr'):null;
      });
      button(row,'Choose product').click();
      stage='product-search';
      const picker=await wait(()=>dialog('Select product'));
      const catalogue=button(picker,'Catalogue');if(catalogue.getAttribute('aria-selected')!=='true')catalogue.click();
      const search=await wait(()=>picker.querySelector('input[type="search"]'));
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(search,plan.sku);
      search.dispatchEvent(new Event('input',{bubbles:true}));
      const selected=await wait(()=>{
        try{return prodigiProductCard(dialog('Select product'),plan.sku,plan.colour);}catch{return null;}
      });
      if(selected.colour){selected.colour.value=selected.value;selected.colour.dispatchEvent(new Event('change',{bubbles:true}));}
      await wait(()=>{
        try {const c=prodigiProductCard(dialog('Select product'),plan.sku,plan.colour);
          return !c.select.disabled&&(!c.colour||c.colour.value===c.value);
        }catch{return false;}
      });
      stage='product-select';
      locationMatches(plan);
      const permission=await chrome.runtime.sendMessage({type:'prodigi:permit',sha256:plan.sha256});
      if(permission?.permitted!==true)throw Error('The blank item changed before selection.');
      locationMatches(plan);
      // Resolve again after React commits the colour; never choose a prefix match/backloader.
      const current=prodigiProductCard(dialog('Select product'),plan.sku,plan.colour);
      if(current.colour&&current.colour.value!==current.value)throw Error('The frame colour did not persist.');
      current.select.click();
      stage='product-readback';
      await wait(()=>!dialog('Select product')&&Array.from(document.querySelectorAll('table tbody tr')).some(r=>
        r.querySelector('[data-test="line-item-preview-'+plan.item_id+'"]')&&prodigiExactRow(r,plan.sku,plan.colour)));
      return {stage}; // Server independently verifies persistence before any artwork handoff.
    }catch{return {stage};}finally{running=false;}
  }
  async function uploadCertificate(plan) {
    let stage='row';
    try {
      const addSlip=await wait(()=>{
        const rows=Array.from(document.querySelectorAll('table tbody tr')).filter(r=>prodigiExactRow(r,plan.sku,plan.colour));
        if(rows.length>1)throw Error('The exact certificate product/frame row is ambiguous.');
        if(rows.length!==1)return null;
        try{return button(document.querySelector('main'),'Add packing slip');}catch{return null;}
      });
      addSlip.click();
      stage='picker';
      const input=await filePickerInput();
      stage='transfer';
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
      locationMatches(plan);stage='permit';
      const permission=await chrome.runtime.sendMessage({type:'prodigi:permit',sha256:hash});
      if(permission?.permitted!==true)throw Error('The draft changed before certificate upload.');
      locationMatches(plan);stage='save';
      const transfer=new DataTransfer();transfer.items.add(file);input.files=transfer.files;
      input.dispatchEvent(new Event('change',{bubbles:true}));
      await wait(()=>!dialog('Select image')&&Array.from(document.querySelectorAll('main a')).some(a=>text(a)==='View packing slip'),240000);
      return {saved:true,stage};
    }catch{return {saved:false,stage};}
  }
  async function upload(plan) {
    if(running) throw Error('An upload is already in progress.');
    running=true;
    let stage='page';
    try {
      locationMatches(plan);
      if(dialogs().length) throw Error('An existing editor requires manual review.');
      if(plan.kind==='certificate')return await uploadCertificate(plan);
      stage='row';
      const row=await wait(()=>{
        const rows=Array.from(document.querySelectorAll('table tbody tr')).filter(r=>prodigiExactRow(r,plan.sku,plan.colour));
        if(rows.length>1) throw Error('The exact product/frame row is ambiguous.');
        if(rows.length!==1) return null;
        try {button(rows[0],'Upload');return rows[0];} catch {return null;}
      });
      button(row,'Upload').click();
      stage='editor';
      const editor=await wait(()=>{
        const e=dialog('Image Editor');if(!e)return null;
        try {button(e,'Add image');return e;} catch {return null;}
      });
      if(!text(editor).includes(plan.sku)) throw Error('Editor product differs.');
      button(editor,'Add image').click();
      stage='picker';
      const input=await filePickerInput();
      stage='transfer';
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
      stage='uploaded';
      const loaded=await wait(()=>{
        const e=dialog('Image Editor');return e&&!dialog('Select image')&&text(e).includes('Uploaded image:')&&e;
      },240000);
      const compact=text(loaded).replace(/\s/g,'');
      if(!Array.isArray(plan.dimensions)||!compact.includes(plan.dimensions.join('x')+'px'))
        throw Error('Uploaded image dimensions differ from the numbered archive.');
      const orientation=plan.dimensions[0]>plan.dimensions[1]?'Landscape':'Portrait';
      stage='orientation';
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
      stage='permit';
      const permission=await chrome.runtime.sendMessage({type:'prodigi:permit',sha256:hash});
      if(permission?.permitted!==true) throw Error('The draft changed before Save.');
      locationMatches(plan);
      stage='save';
      button(dialog('Image Editor'),'Save').click();
      await wait(()=>!dialog('Image Editor'),120000);
      return {saved:true,stage};
    } catch {
      return {saved:false,stage};
    } finally {running=false;}
  }
  chrome.runtime.onMessage.addListener((message,sender,reply)=>{
    if(sender.id!==chrome.runtime.id) return;
    if(message?.type==='prodigi:ready') {
      const match=location.pathname.match(/^\/orders\/([A-Za-z0-9-]+)\/detail$/);
      reply({ready:document.readyState==='complete'&&Boolean(match)&&
        Array.from(document.querySelectorAll('main h1')).some(e=>text(e).startsWith(match[1]))});return;
    }
    if(message?.type==='prodigi:upload') {
      upload(message.plan).then(reply,()=>reply({saved:false}));return true;
    }
    if(message?.type==='prodigi:product') {
      selectProduct(message.plan).then(reply,()=>reply({stage:'product'}));return true;
    }
  });
})();
