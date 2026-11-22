'use strict';
function prodigiShippingQuotes(select) {
  return Array.from(select.options).filter(o=>!o.disabled).map(o=>{
    const m=o.textContent.trim().match(/^(Budget|Standard(?: ?Plus)?|Express|Overnight):\s*([$£€])\s*([0-9]+(?:,[0-9]{3})*)(?:\.([0-9]{2}))?$/i);
    if(!m)throw Error('An available shipping quote cannot be read.');
    return {service:m[1].toLowerCase().replace(/\s/g,''),cents:Number(m[3].replaceAll(',',''))*100+Number(m[4]||0),currency:m[2]};
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
  async function wait(fn,timeout=120000){const end=Date.now()+timeout;do{const v=fn();if(v)return v;await delay(200);}while(Date.now()<end);throw Error('The expected QA control did not finish loading.');}
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
      return {name:text(n),asset:null};
    });
    return rows;
  }
  async function inspectInserts(plan){
    pin(plan);
    // The artwork row can render before Prodigi loads the inserts controls.
    const edit=await wait(()=>{try{return uniqueButton(document.querySelector('main'),'View & edit');}catch{return null;}});
    pin(plan);edit.click();
    let saved=[];
    try {
      const modal=await wait(insertDialog);
      // Read the currently saved selection only. Never select, assign or save a set.
      saved=await wait(()=>{const rows=insertRows(modal);return rows.length?rows:null;},20000).catch(()=>[]);
    } finally {
      const open=insertDialog();if(open)uniqueButton(open,'Cancel').click();
      await wait(()=>!insertDialog());
    }
    pin(plan);
    const main=text(document.querySelector('main'));
    return {set_name:'',saved,expected:[],available:!(/inserts are unavailable|inserts are not available|will not be charged for unavailable inserts/i.test(main))};
  }

  function taxControl(){
    const controls=Array.from(document.querySelectorAll('#taxCollectedCheckbox')).filter(visible);
    if(controls.length!==1)return null;
    const e=controls[0],label=text(e.parentElement);
    if(label!=='I declare that this order has already had sales tax collected.')return null;
    if(e.getAttribute('role')!=='checkbox'&&!(e.tagName==='INPUT'&&e.type==='checkbox'))return null;
    return e;
  }
  function taxChecked(e){return e.getAttribute('role')==='checkbox'?e.getAttribute('aria-checked')==='true':e.checked===true;}
  async function declareTax(plan,permit){
    if(!plan.tax_declaration)return null;
    if(permit?.tax_declaration!==true)throw Error('The sales-tax declaration was not authorised for this draft.');
    let control=plan.tax_required?await wait(taxControl):taxControl();
    if(!control)return null;
    pin(plan);
    if(!taxChecked(control)){if(control.disabled)throw Error('The sales-tax declaration is disabled.');control.click();await wait(()=>{const e=taxControl();return e&&taxChecked(e);});await delay(700);}
    pin(plan);control=taxControl();
    if(!control||!taxChecked(control))throw Error('The sales-tax declaration was not saved.');
    return true;
  }
  async function run(plan){
    let stage='product-row';
    try {
      pin(plan);
      if(Array.from(document.querySelectorAll('[role="dialog"]')).some(visible))throw Error('Close the existing order editor before QA.');
      const row=await wait(()=>prodigiPinnedRow(document.querySelectorAll('table tbody tr'),plan));
      const quality=text(row.querySelector('[title="Image quality"]'));
      if(!quality)throw Error('Supplier image quality is not visible.');
      stage='inserts';
      const inserts=await inspectInserts(plan);
      stage='shipping';
      const selects=Array.from(document.querySelectorAll('main select')).filter(s=>Array.from(s.options).some(o=>/^(Budget|Standard(?: ?Plus)?|Express|Overnight):\s*[$£€]/.test(o.textContent)));
      if(selects.length!==1)throw Error('A unique shipping selector is required.');
      const select=selects[0],options=prodigiShippingQuotes(select),current=select.value.toLowerCase();
      if(!options.some(o=>o.service===current))throw Error('Selected shipping service is unknown.');
      const target=prodigiCheapestShipping(options,plan.shipping_intent,current);
      const permit=await chrome.runtime.sendMessage({type:'prodigi:qa-permit',evidence:{options,current,target}});
      if(permit?.permitted!==true)throw Error('The exact draft or shipping quotes changed before QA.');
      pin(plan);
      if(target!==current){const option=Array.from(select.options).find(o=>o.value.toLowerCase()===target);if(!option)throw Error('Chosen shipping quote disappeared.');select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));await delay(1000);}
      pin(plan);
      const shippingNow=Array.from(document.querySelectorAll('main select')).filter(s=>Array.from(s.options).some(o=>/^(Budget|Standard(?: ?Plus)?|Express|Overnight):\s*[$£€]/.test(o.textContent)));
      if(shippingNow.length!==1||shippingNow[0].value.toLowerCase()!==target)throw Error('Shipping selection was not saved.');
      stage='tax-declaration';
      const tax_collected=await declareTax(plan,permit);
      return {evidence:{...(plan.exact_item?{item_id:plan.item_id}:{}),tax_collected,quality,sku:plan.sku,colour:plan.colour,shipping:{options:prodigiShippingQuotes(shippingNow[0]),selected:target},inserts}};
    }catch(error){return {error:('QA '+stage+': '+String(error.message||'Dashboard QA stopped')).slice(0,240)};}
  }
  let running=false;
  chrome.runtime.onMessage.addListener((message,sender,reply)=>{
    if(sender.id!==chrome.runtime.id||message?.type!=='prodigi:qa')return;
    if(running){reply({error:'A QA pass is already running.'});return;}
    running=true;run(message.plan).then(reply,()=>reply({error:'Dashboard QA stopped.'})).finally(()=>{running=false;});return true;
  });
})();
