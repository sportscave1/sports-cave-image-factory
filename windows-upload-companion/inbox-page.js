'use strict';
const inboxAddressFields={name:'recipient-name-field',line1:'recipient-address-line-1-field',
 line2:'recipient-address-line-2-field',townOrCity:'recipient-address-town-field',
 stateOrCounty:'recipient-address-county-field',postalOrZipCode:'recipient-address-postcode-field'};
function inboxAddressValues(recipient){return {name:recipient.name,...recipient.address};}
function inboxCountry(code){return {AU:'Australia',US:'United States',GB:'United Kingdom',NZ:'New Zealand',CA:'Canada'}[code];}
if(typeof module!=='undefined')module.exports={inboxAddressFields,inboxAddressValues,inboxCountry};
(()=>{
 if(typeof document==='undefined')return;
 let running=false;
 const text=e=>(e?.innerText||e?.textContent||'').replace(/\s+/g,' ').trim();
 const visible=e=>e&&e.isConnected&&e.getClientRects().length;
 const dialogs=()=>Array.from(document.querySelectorAll('[role="dialog"]')).filter(visible);
 const normal=v=>String(v||'').replace(/\s+/g,' ').trim().toLowerCase();
 const button=(scope,name)=>{
  const found=Array.from(scope.querySelectorAll('button')).filter(e=>visible(e)&&!e.disabled&&text(e)===name);
  if(found.length!==1)throw Error('Inbox needs a unique '+name+' control.');return found[0];
 };
 const wait=fn=>prodigiObserveReady(fn,{timeout:30000});
 function pin(plan){
  if(location.href!==plan.order_url||!/^https:\/\/dashboard\.prodigi\.com\/orders\/[A-Za-z0-9-]+\/detail$/.test(plan.order_url)||
     !Array.from(document.querySelectorAll('main h1')).some(e=>text(e).split(/\s/)[0]===plan.order_id)||
     !text(document.querySelector('main')).includes(plan.reference))throw Error('Inbox order identity changed.');
 }
 function paused(){
  // The current countdown/hold controls, not a historical Order paused entry.
  const main=document.querySelector('main');
  return prodigiIndefiniteHold(main,text,visible)||Array.from(main.querySelectorAll('button')).some(e=>visible(e)&&text(e)==='Pause indefinitely');
 }
 function values(modal){
  const result={};
  for(const [key,id] of Object.entries(inboxAddressFields)){
   const all=modal.querySelectorAll('[id="'+id+'"]');
   if(all.length!==1||!visible(all[0])||all[0].disabled)throw Error('Inbox address field changed.');
   result[key]=all[0];
  }
  const country=modal.querySelector('#recipient_country_field');
  if(!country||!country.disabled)throw Error('Inbox country control changed.');
  return {inputs:result,country:country.value};
 }
 async function run(plan){
  pin(plan);if(dialogs().length||!paused())throw Error('Inbox requires a closed editor and paused order.');
  const permit=await chrome.runtime.sendMessage({type:'inbox:permit'});
  if(permit?.permitted!==true||permit.order_id!==plan.order_id||permit.action!==plan.action)throw Error('Inbox write was not permitted.');
  pin(plan);if(!paused())throw Error('Order left its edit window.');
  if(plan.action==='hold'){
   const held=()=>prodigiIndefiniteHold(document.querySelector('main'),text,visible);
   if(!held()){
    button(document.querySelector('main'),'Pause indefinitely').click();
    const state=await wait(()=>{pin(plan);return held()?true:dialogs()[0]||null;});
    if(state!==true){
     if(!/pause/i.test(text(state))||/terms|conditions|agreement/i.test(text(state)))throw Error('Pause confirmation needs review.');
     const choices=Array.from(state.querySelectorAll('button')).filter(e=>visible(e)&&!e.disabled&&['Pause indefinitely','Pause order','Confirm'].includes(text(e)));
     if(choices.length!==1)throw Error('Pause confirmation is ambiguous.');choices[0].click();
    }
    await wait(()=>{pin(plan);return held();});
   }
   pin(plan);return {evidence:{indefinite_hold:true}};
  }
  if(plan.action!=='address')throw Error('Unsupported Inbox action.');
  button(document.querySelector('main'),'Edit address').click();
  const modal=await wait(()=>dialogs().find(e=>Array.from(e.querySelectorAll('h1,h2')).some(h=>text(h)==='Edit address')));
  try{
   pin(plan);const form=values(modal),before=inboxAddressValues(plan.before_recipient),after=inboxAddressValues(plan.recipient);
   if(normal(form.country)!==normal(inboxCountry(after.countryCode))||before.countryCode!==after.countryCode)throw Error('Country changes require review.');
   for(const [key,input] of Object.entries(form.inputs))if(normal(input.value)!==normal(before[key]))throw Error('Saved address changed before editing.');
   const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
   for(const key of Object.keys(form.inputs)){
    const input=values(modal).inputs[key];
    setter.call(input,after[key]||'');input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
   }
   // Resolve after React commits; never save a partially applied replacement.
   await wait(()=>{pin(plan);const current=values(modal);return Object.entries(current.inputs).every(([key,input])=>normal(input.value)===normal(after[key]));});
   pin(plan);if(!paused())throw Error('Order left its edit window.');
   button(modal,'Save and close').click();
   await wait(()=>{pin(plan);return !dialogs().includes(modal);});
   return {evidence:{address_saved:true}};
  }catch(error){
   // Cancel an unsaved editor only. Never click Save again after an uncertain response.
   if(dialogs().includes(modal)){try{button(modal,'Cancel changes').click();}catch{}}
   throw error;
  }
 }
 chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  if(sender.id!==chrome.runtime.id||message?.type!=='inbox:run')return;
  if(running){reply({error:'Inbox operation already running.'});return;}
  running=true;run(message.plan).then(reply,()=>reply({error:'Inbox action not confirmed; review the exact order.'})).finally(()=>{running=false;});return true;
 });
})();
