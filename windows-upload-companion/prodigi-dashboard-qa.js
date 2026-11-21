'use strict';
function prodigiShippingQuotes(select) {
  return Array.from(select.options).filter(o=>!o.disabled).map(o=>{
    const m=o.textContent.trim().match(/^(Budget|Standard|Express):\s*([$£€])\s*([0-9]+(?:,[0-9]{3})*)(?:\.([0-9]{2}))?$/i);
    if(!m)throw Error('An available shipping quote cannot be read.');
    return {service:m[1].toLowerCase(),cents:Number(m[3].replaceAll(',',''))*100+Number(m[4]||0),currency:m[2]};
  });
}
function prodigiCheapestShipping(options,intent,current) {
  if(!options.length||new Set(options.map(o=>o.currency)).size!==1||new Set(options.map(o=>o.service)).size!==options.length)throw Error('Shipping quotes are ambiguous.');
  if(intent==='express') {if(!options.some(o=>o.service==='express'))throw Error('Express is unavailable.');return 'express';}
  if(intent!=='standard')throw Error('Customer shipping service is unknown.');
  const minimum=Math.min(...options.map(o=>o.cents)),choices=options.filter(o=>o.cents===minimum).map(o=>o.service);
  return choices.includes(current)?current:choices[0];
}
if(typeof module!=='undefined')module.exports={prodigiShippingQuotes,prodigiCheapestShipping};
(() => {
  if(typeof document==='undefined')return;
  const delay=ms=>new Promise(r=>setTimeout(r,ms));
  const text=e=>(e?.innerText||e?.textContent||'').replace(/\s+/g,' ').trim();
  const visible=e=>e&&e.isConnected&&e.getClientRects().length;
  async function wait(fn,timeout=20000){const end=Date.now()+timeout;do{const v=fn();if(v)return v;await delay(200);}while(Date.now()<end);throw Error('The expected QA control did not finish loading.');}
  function uniqueButton(scope,label){const all=Array.from(scope.querySelectorAll('button')).filter(e=>visible(e)&&!e.disabled&&(e.getAttribute('aria-label')||text(e))===label);if(all.length!==1)throw Error('A unique '+label+' control is required.');return all[0];}
  function pin(plan){
    const actual=new URL(location.href),wanted=new URL(plan.order_url);
    if(actual.origin!==wanted.origin||actual.pathname!==wanted.pathname||actual.search||actual.hash||
       !Array.from(document.querySelectorAll('main h1')).some(e=>text(e).startsWith(plan.order_id))||
       !text(document.querySelector('main')).includes(plan.reference))throw Error('The exact QA order changed.');
  }
  function insertDialog(){return Array.from(document.querySelectorAll('[role="dialog"]')).find(e=>visible(e)&&Array.from(e.querySelectorAll('h1,h2')).some(h=>text(h)==='Inserts on this order'));}
  function insertRows(scope){
    const rows=Array.from(scope.querySelectorAll('[data-test^="insert-item-"][data-test$="-name"]')).filter(visible).map(n=>{
      const images=Array.from(n.closest('li').querySelectorAll('img')).filter(visible);
      const ids=images.map(i=>{try{const u=new URL(i.currentSrc||i.src);return u.hostname==='live-services.pwinty.com'?u.pathname.match(/\/image-library\/(?:transform|image)\/([A-Za-z0-9-]+)\//)?.[1]:null;}catch{return null;}}).filter(Boolean);
      return {name:text(n),asset:ids.length&&new Set(ids).size===1?ids[0]:null};
    });
    return rows.length>0&&rows.every(r=>r.asset)?rows:null;
  }
  async function inspectInserts(plan){
    pin(plan);uniqueButton(document.querySelector('main'),'View & edit').click();
    const modal=await wait(insertDialog);
    let saved,expected;
    try {
      saved=await wait(()=>insertRows(modal));
      const selects=Array.from(modal.querySelectorAll('select')).filter(e=>visible(e)&&Array.from(e.options).some(o=>o.textContent.trim()===plan.branding_set));
      if(selects.length!==1)throw Error('SC EDITION BRANDING cannot be uniquely found.');
      const options=Array.from(selects[0].options).filter(o=>o.textContent.trim()===plan.branding_set);
      if(options.length!==1)throw Error('Branding set selection is ambiguous.');
      selects[0].value=options[0].value;selects[0].dispatchEvent(new Event('change',{bubbles:true}));
      (await wait(()=>{try{return uniqueButton(modal,'Use this set');}catch{return null;}})).click();
      // Use only the unsaved preview to identify the set's exact image assets.
      // Cancel is mandatory; this worker never assigns or saves paid inserts.
      expected=await wait(()=>{const r=insertRows(modal);return r&&r.length===2&&r.some(i=>i.name==='Round packaging sticker')&&r.some(i=>i.name==='Packing slip (colour)')&&r;});
    } finally {
      const open=insertDialog();if(open)uniqueButton(open,'Cancel').click();
      await wait(()=>!insertDialog());
    }
    pin(plan);
    uniqueButton(document.querySelector('main'),'View & edit').click();
    try {
      const reopened=await wait(insertDialog),confirmed=await wait(()=>insertRows(reopened));
      if(JSON.stringify(confirmed)!==JSON.stringify(saved))throw Error('Saved inserts changed during the check.');
    } finally {const open=insertDialog();if(open)uniqueButton(open,'Cancel').click();await wait(()=>!insertDialog());}
    const main=text(document.querySelector('main'));
    return {set_name:plan.branding_set,saved,expected,available:!(/inserts are unavailable|inserts are not available|will not be charged for unavailable inserts/i.test(main))};
  }
  async function run(plan){
    try {
      pin(plan);
      if(Array.from(document.querySelectorAll('[role="dialog"]')).some(visible))throw Error('Close the existing order editor before QA.');
      const row=await wait(()=>{const rows=Array.from(document.querySelectorAll('table tbody tr')).filter(r=>prodigiExactRow(r,plan.sku,plan.colour));if(rows.length>1)throw Error('The product/frame row is ambiguous.');return rows[0];});
      const quality=text(row.querySelector('[title="Image quality"]'));
      if(!quality)throw Error('Supplier image quality is not visible.');
      const inserts=await inspectInserts(plan);
      const selects=Array.from(document.querySelectorAll('main select')).filter(s=>Array.from(s.options).some(o=>/^(Budget|Standard|Express):\s*[$£€]/.test(o.textContent)));
      if(selects.length!==1)throw Error('A unique shipping selector is required.');
      const select=selects[0],options=prodigiShippingQuotes(select),current=select.value.toLowerCase();
      if(!options.some(o=>o.service===current))throw Error('Selected shipping service is unknown.');
      const target=prodigiCheapestShipping(options,plan.shipping_intent,current);
      const permit=await chrome.runtime.sendMessage({type:'prodigi:qa-permit',evidence:{options,current,target}});
      if(permit?.permitted!==true)throw Error('The exact draft or shipping quotes changed before QA.');
      pin(plan);
      if(target!==current){const option=Array.from(select.options).find(o=>o.value.toLowerCase()===target);if(!option)throw Error('Chosen shipping quote disappeared.');select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));await delay(1000);}
      pin(plan);
      const shippingNow=Array.from(document.querySelectorAll('main select')).filter(s=>Array.from(s.options).some(o=>/^(Budget|Standard|Express):\s*[$£€]/.test(o.textContent)));
      if(shippingNow.length!==1||shippingNow[0].value.toLowerCase()!==target)throw Error('Shipping selection was not saved.');
      return {evidence:{quality,sku:plan.sku,colour:plan.colour,shipping:{options:prodigiShippingQuotes(shippingNow[0]),selected:target},inserts}};
    }catch(error){return {error:String(error.message||'Dashboard QA stopped').slice(0,240)};}
  }
  let running=false;
  chrome.runtime.onMessage.addListener((message,sender,reply)=>{
    if(sender.id!==chrome.runtime.id||message?.type!=='prodigi:qa')return;
    if(running){reply({error:'A QA pass is already running.'});return;}
    running=true;run(message.plan).then(reply,()=>reply({error:'Dashboard QA stopped.'})).finally(()=>{running=false;});return true;
  });
})();
