(() => {
  'use strict';
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const visible=e=>e&&e.isConnected&&e.getClientRects().length;
  const text=e=>(e?.textContent||'').replace(/\s+/g,' ').trim();
  const dialogs=()=>Array.from(document.querySelectorAll('[role="dialog"]')).filter(visible);
  const dialog=name=>dialogs().find(e=>Array.from(e.querySelectorAll('h1,h2')).some(h=>text(h)===name));
  const button=(scope,label)=>{
    const name=e=>e.getAttribute('aria-label')||text(e)||Array.from(e.querySelectorAll('img')).map(i=>i.alt).join(' ');
    const found=Array.from(scope.querySelectorAll('button')).filter(e=>visible(e)&&name(e)===label&&!e.disabled);
    if(found.length!==1) throw Error('A unique '+label+' control is required.');
    return found[0];
  };
  async function wait(check,timeout=120000) {
    const end=Date.now()+timeout;
    do {const result=check();if(result)return result;await delay(250);}while(Date.now()<end);
    throw Error('Prodigi did not reach the expected upload state.');
  }
  function locationMatches(plan) {
    if(location.href!==plan.order_url) throw Error('The supplier order changed.');
    const sandbox=Array.from(document.querySelectorAll('strong')).some(e=>text(e)==='Sandbox environment');
    if(sandbox!==(plan.environment==='sandbox')) throw Error('Supplier environment differs.');
    if(!Array.from(document.querySelectorAll('h1')).some(e=>text(e).startsWith(plan.order_id)))
      throw Error('The exact supplier order heading is missing.');
    if(!document.body.innerText.includes(plan.reference)) throw Error('The exact order reference is missing.');
  }
  let running=false;
  async function upload(plan) {
    if(running) throw Error('An upload is already in progress.');
    running=true;
    let stage='page';
    try {
      locationMatches(plan);
      if(dialogs().length) throw Error('An existing editor requires manual review.');
      stage='row';
      const rows=Array.from(document.querySelectorAll('table tbody tr')).filter(row=>{
        const tokens=text(row).split(/\s+/);
        return tokens.includes(plan.sku) && (!plan.colour ||
          Array.from(row.querySelectorAll('strong')).some(e=>text(e).toLowerCase()===plan.colour.toLowerCase()));
      });
      if(rows.length!==1) throw Error('The exact product/frame row is ambiguous.');
      button(rows[0],'Upload').click();
      stage='editor';
      const editor=await wait(()=>dialog('Image Editor'));
      if(!text(editor).includes(plan.sku)) throw Error('Editor product differs.');
      button(editor,'Add image').click();
      stage='picker';
      const picker=await wait(()=>dialog('Select image'));
      const input=picker.querySelector('input[data-test="image-library-upload-from-file-input"][type="file"]');
      if(!input) throw Error('Prodigi upload input changed.');
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
      button(loaded,'fit').click();
      await delay(500); // Let the editor commit its orientation/fit state before Save.
      stage='permit';
      const permission=await chrome.runtime.sendMessage({type:'prodigi:permit',sha256:hash});
      if(permission?.permitted!==true) throw Error('The draft changed before Save.');
      locationMatches(plan);
      stage='save';
      button(loaded,'Save').click();
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
  });
})();
