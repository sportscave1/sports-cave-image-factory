'use strict';
// Inbox has no status bar. It shares the Orders native writer and paired credential.
let inboxActive=null,inboxTickRunning=false;
const inboxAlarm='sports-cave-inbox-queue';
function inboxValidRecipient(recipient,replacement=true){
 return !!recipient&&typeof recipient.name==='string'&&recipient.name.length<=150&&recipient.address&&
 ['AU','US','GB','NZ','CA'].includes(recipient.address.countryCode)&&
 (replacement?['line1','townOrCity','stateOrCounty','postalOrZipCode']:['line1','townOrCity','postalOrZipCode']).every(k=>typeof recipient.address[k]==='string'&&recipient.address[k].length>0&&recipient.address[k].length<=150)&&
 (recipient.address.line2==null||typeof recipient.address.line2==='string'&&recipient.address.line2.length<=150);
}
function inboxValidPlan(plan){
 return !!plan&&/^inbox_companion_request:[a-f0-9]{64}$/.test(plan.key)&&/^[A-Za-z0-9_-]{43}$/.test(plan.token)&&
  /^[A-Za-z0-9-]{1,100}$/.test(plan.order_id)&&plan.order_url===`https://dashboard.prodigi.com/orders/${plan.order_id}/detail`&&
  typeof plan.reference==='string'&&plan.reference.length>0&&plan.reference.length<=100&&['address','hold'].includes(plan.action)&&
  (plan.action!=='address'||(inboxValidRecipient(plan.recipient)&&inboxValidRecipient(plan.before_recipient,false)&&plan.recipient.address.countryCode===plan.before_recipient.address.countryCode));
}
async function inboxRequest(action,plan=null,result=null,scanOnly=false){
 const token=(await chrome.storage.local.get('staffQueueCredential')).staffQueueCredential;
 if(!token)throw Error('Pair this desktop first.');
 const body=plan?{key:plan.key,token:plan.token,order_id:plan.order_id,
  ...(action==='finish'?{evidence:result?.evidence||null,error:result?.error||''}:{})}:{};
 const response=await fetch(osOrigin+'/api/inbox-companion/'+action,{method:'POST',
  headers:{Authorization:'Bearer '+token,'Content-Type':'application/json',...(scanOnly?{'X-Inbox-Scan-Only':'1'}:{})},body:JSON.stringify(body),
  credentials:'omit',signal:AbortSignal.timeout(150000)});
 if(!response.ok)throw Error('Inbox Companion request was not acknowledged.');
 return response.json();
}
async function inboxQueueTick(){
 if(inboxTickRunning)return false;
 const scanOnly=ordersTickRunning;
 inboxTickRunning=true;if(!scanOnly)ordersTickRunning=true;
 const keepAlive=setInterval(()=>{void chrome.storage.local.get('staffQueueCredential').catch(()=>{});},20000);
 try{
  if(!(await chrome.storage.local.get('staffQueueCredential')).staffQueueCredential)return false;
  // Intake can flag an urgent request while an upload runs, without touching its tab.
  if(scanOnly){await inboxRequest('tick',null,null,true);return true;}
  const interrupted=(await chrome.storage.local.get('inboxBrowserPending')).inboxBrowserPending;
  if(interrupted){
   // Finish is readback only. Never send the browser another uncertain Save/pause.
   await inboxRequest('finish',interrupted,{error:'Interrupted Inbox operation; review the same order.'});
   await chrome.storage.local.remove('inboxBrowserPending');
  }
  const result=await inboxRequest('tick');if(!result.browser)return true;
  const plan=result.browser;if(!inboxValidPlan(plan))throw Error('Invalid Inbox handoff.');
  let tab=await prodigiWorkerTab(plan);
  if(!await prodigiWaitForPage(tab,false,30,plan.order_url))throw Error('Inbox order page is unavailable.');
  inboxActive={plan,tab:tab.id};
  await chrome.storage.local.set({inboxBrowserPending:plan});
  const evidence=await chrome.tabs.sendMessage(tab.id,{type:'inbox:run',plan});
  await inboxRequest('finish',plan,evidence);
  await chrome.storage.local.remove('inboxBrowserPending');
  return true;
 }catch{return false;}
 finally{
  inboxActive=null;inboxTickRunning=false;clearInterval(keepAlive);
  if(!scanOnly){
   ordersTickRunning=false;
   // Edge can coalesce both alarms. Always wake Orders after yielding its slot
   // so an idle Inbox poll cannot repeatedly consume the Orders alarm.
   if(typeof continueOrdersSoon==='function')continueOrdersSoon();
  }
 }
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
 if(sender.id!==chrome.runtime.id||message?.type!=='inbox:permit'||!inboxActive||sender.tab?.id!==inboxActive.tab)return;
 inboxRequest('permit',inboxActive.plan).then(reply,()=>reply({permitted:false}));return true;
});
async function ensureInboxAlarm(){
 if(!(await chrome.storage.local.get('staffQueueCredential')).staffQueueCredential)return;
 if(!await chrome.alarms.get(inboxAlarm))await chrome.alarms.create(inboxAlarm,{periodInMinutes:0.5});
}
chrome.alarms.onAlarm.addListener(alarm=>{if(alarm.name===inboxAlarm)void inboxQueueTick();});
chrome.runtime.onStartup.addListener(()=>{void ensureInboxAlarm();});
chrome.runtime.onInstalled.addListener(()=>{void ensureInboxAlarm();});
if(chrome.storage.onChanged)chrome.storage.onChanged.addListener((changes,area)=>{
 if(area==='local'&&changes.staffQueueCredential)void ensureInboxAlarm();
});
void ensureInboxAlarm();
if(typeof module!=='undefined')module.exports={inboxValidPlan};
