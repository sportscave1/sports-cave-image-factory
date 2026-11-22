'use strict';

// Only server-issued exact drafts. No API key, supplier requests or Submit click.
let prodigiBrowserTransfer = null;
const ordersDelay = ms => new Promise(resolve => setTimeout(resolve,ms));
function prodigiOrderAddress(address,expected) {
  try {
    const actual=new URL(address),pinned=new URL(expected);
    return actual.origin===pinned.origin && actual.pathname===pinned.pathname && !actual.hash &&
      !actual.username&&!actual.password&&Array.from(actual.searchParams.keys()).every(
        key=>['imageLibraryType','imageLibraryFileType'].includes(key));
  } catch {return false;}
}
function prodigiPlanValid(plan) {
  const host=plan?.environment==='sandbox'?'sandbox-beta-dashboard.pwinty.com':
    plan?.environment==='live'?'dashboard.prodigi.com':null;
  if(plan?.replace_artwork!==undefined && (plan.replace_artwork!==true||host!=='dashboard.prodigi.com'||plan.exact_item!==true||
    !/^prodigi_prepare:\d+$/.test(plan.key)||!/^[A-Za-z0-9_-]{43}$/.test(plan.token)||!/^[A-Za-z0-9-]{1,100}$/.test(plan.item_id)))return false;
  if(plan?.kind==='qa' && plan.items!==undefined && (!Array.isArray(plan.items)||plan.items.length<2||plan.items.length>20||
    plan.exact_item!==true||new Set(plan.items.map(r=>r?.item_id)).size!==plan.items.length||
    !plan.items.some(r=>r?.item_id===plan.item_id&&r.sku===plan.sku&&r.colour===plan.colour)||
    plan.items.some(r=>!r||!/^[A-Za-z0-9-]{1,100}$/.test(r.item_id)||!/^GLOBAL-(CFP|FAP)-A[1-4]$/.test(r.sku)||
      !(r.sku.startsWith('GLOBAL-FAP-')?r.colour==='':['Black','Natural','White'].includes(r.colour)))))return false;
  if(plan?.kind==='product')return Boolean(host==='dashboard.prodigi.com' && /^[A-Za-z0-9-]{1,100}$/.test(plan.order_id) && /^[A-Za-z0-9-]{1,100}$/.test(plan.item_id) && plan.order_url===`https://${host}/orders/${plan.order_id}/detail` && /^product:prodigi_prepare:\d+$/.test(plan.key) && /^[A-Za-z0-9_-]{43}$/.test(plan.token) && /^[a-f0-9]{64}$/.test(plan.sha256) && /^GLOBAL-(CFP|FAP)-A[1-4]$/.test(plan.sku) && (plan.sku.startsWith('GLOBAL-FAP-')?plan.colour==='':['Black','Natural','White'].includes(plan.colour)) && typeof plan.reference==='string');
  if(plan?.kind==='qa')return Boolean(host==='dashboard.prodigi.com' && plan.environment==='live' && /^[A-Za-z0-9-]{1,100}$/.test(plan.order_id) && plan.order_url===`https://${host}/orders/${plan.order_id}/detail` && /^prodigi_prepare:\d+$/.test(plan.key) && /^[A-Za-z0-9_-]{43}$/.test(plan.token) && typeof plan.reference==='string' && typeof plan.sku==='string' && typeof plan.colour==='string' && ['standard','express'].includes(plan.shipping_intent) && plan.branding_set==='SC EDITION BRANDING');
  return Boolean(host && (plan.kind===undefined||plan.kind==='certificate') && /^[A-Za-z0-9-]{1,100}$/.test(plan.order_id) &&
    plan.order_url===`https://${host}/orders/${plan.order_id}/detail` &&
    (plan.kind==='certificate'?/^https:\/\/sports-cave-image-factory\.onrender\.com\/api\/prodigi-document\/[A-Za-z0-9_-]{43}$/:/^https:\/\/sports-cave-image-factory\.onrender\.com\/api\/prodigi-artwork\/[A-Za-z0-9_-]{43}$/).test(plan.artwork_url) &&
    /^[a-f0-9]{64}$/.test(plan.sha256) && Number.isSafeInteger(plan.bytes) && plan.bytes>0 && plan.bytes<=128*1024*1024 &&
    (plan.kind==='certificate'?/^SC-\d+-certificate-[a-f0-9]{16}\.pdf$/:/^SC-\d+-[a-f0-9]{16}-[a-f0-9]{8}\.jpg$/).test(plan.filename) && typeof plan.reference==='string');
}
async function prodigiQAReceipt(plan,action,evidence=null,error='') {
  const token=(await chrome.storage.local.get('staffQueueCredential')).staffQueueCredential;
  if(!token)throw Error('Desktop pairing unavailable.');
  const response=await fetch(osOrigin+'/api/orders-companion/qa/'+action,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify({key:plan.key,token:plan.token,evidence,...(error?{error}: {})}),credentials:'omit',signal:AbortSignal.timeout(150000)});
  if(!response.ok)throw Error('The pinned QA receipt could not be verified.');return response.json();
}
async function prodigiReceipt(plan,action,stage='readback',error='') {
  if(plan.kind==='qa')return prodigiQAReceipt(plan,action,null,'Interrupted QA; recheck the saved order without repeating an upload.');
  const token=(await chrome.storage.local.get('staffQueueCredential')).staffQueueCredential;
  if(!token) throw Error('Desktop pairing is unavailable.');
  const response=await fetch(osOrigin+'/api/orders-companion/browser/'+action,{
    method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
    body:JSON.stringify({key:plan.key,token:plan.token,...(action==='permit'?{sha256:plan.sha256}:{stage,...(error?{error:String(error).slice(0,240)}:{})})}),credentials:'omit',signal:AbortSignal.timeout(150000)});
  if(!response.ok) throw Error('The exact draft could not be verified.');
  return response.json();
}
async function prodigiBrowserRun(plan) {
  if(!prodigiPlanValid(plan)) throw Error('Orders browser handoff rejected.');
  await chrome.storage.local.set({ordersBrowserPending:plan});
  let stage='download';
  try {
    if(plan.kind==='qa'||plan.kind==='product'){
      const tab=await chrome.tabs.create({url:plan.order_url,active:false});prodigiBrowserTransfer={plan,bytes:new Uint8Array(),tab:tab.id};
      let ready=false;for(let n=0;n<30;n++){try{ready=(await chrome.tabs.sendMessage(tab.id,{type:'prodigi:ready'}))?.ready;if(ready)break;}catch{}await ordersDelay(1000);}
      if(!ready)throw Error('Sign into Prodigi before checking the saved order.');
      const result=await chrome.tabs.sendMessage(tab.id,{type:plan.kind==='product'?'prodigi:product':'prodigi:qa',plan});
      return plan.kind==='product'?await prodigiReceipt(plan,'finish',result?.stage||'product'):await prodigiQAReceipt(plan,'finish',result?.evidence||null,result?.error||'');
    }
    const file=await fetch(plan.artwork_url,{credentials:'omit',redirect:'error',signal:AbortSignal.timeout(150000)});
    if(!file.ok || (file.headers.get('content-length') && Number(file.headers.get('content-length'))!==plan.bytes))
      throw Error('The pinned JPG is unavailable.');
    const bytes=new Uint8Array(await file.arrayBuffer());
    if(bytes.length!==plan.bytes) throw Error('The JPG byte count changed.');
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
    if(hash!==plan.sha256) throw Error('The numbered JPG checksum changed.');
    stage='open';
    const tab=await chrome.tabs.create({url:plan.order_url,active:false});
    prodigiBrowserTransfer={plan,bytes,tab:tab.id};
    let ready=false;
    for(let n=0;n<60;n++) {
      try {ready=(await chrome.tabs.sendMessage(tab.id,{type:'prodigi:ready'}))?.ready; if(ready) break;} catch {}
      await ordersDelay(1000);
    }
    if(!ready) {stage='signin';throw Error('Sign into Prodigi in Edge, then review the same draft.');}
    const result=await chrome.tabs.sendMessage(tab.id,{type:'prodigi:upload',plan});
    stage=result?.stage||'page';
    if(!result?.saved) throw Error(result?.error||'The companion stopped before a confirmed artwork Save.');
    return await prodigiReceipt(plan,'finish',stage);
  } catch(error) {
    // Read back this same item; never repeat an uncertain Save or upload.
    return await prodigiReceipt(plan,'finish',stage,String(error.message||'Browser handoff interrupted'));
  } finally {
    prodigiBrowserTransfer=null;
    await chrome.storage.local.remove('ordersBrowserPending');
  }
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  const job=prodigiBrowserTransfer;
  if(!job || sender.frameId!==0 || sender.tab?.id!==job.tab || !prodigiOrderAddress(sender.url,job.plan.order_url)) return;
  if(message?.type==='prodigi:qa-permit'&&job.plan.kind==='qa'){prodigiQAReceipt(job.plan,'permit',message.evidence).then(reply,()=>reply({error:true}));return true;}
  if(message?.type==='prodigi:chunk') {
    const offset=message.offset;
    if(!Number.isSafeInteger(offset)||offset<0||offset>=job.bytes.length||offset%262144) {reply({error:true});return;}
    const chunk=job.bytes.subarray(offset,Math.min(offset+262144,job.bytes.length));
    let binary=''; for(let n=0;n<chunk.length;n+=8192) binary+=String.fromCharCode(...chunk.subarray(n,n+8192));
    reply({base64:btoa(binary)});return;
  }
  if(message?.type==='prodigi:permit') {
    if(message.sha256!==job.plan.sha256) {reply({error:true});return;}
    prodigiReceipt(job.plan,'permit').then(reply,()=>reply({error:true}));return true;
  }
});
