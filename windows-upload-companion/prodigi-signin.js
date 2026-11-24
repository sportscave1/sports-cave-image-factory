'use strict';

// No passwords in storage, queue results, clipboard, progress or diagnostics.
const prodigiSigninDetail='Sign into Prodigi in Edge. Waiting orders resume automatically after sign-in.';
async function prodigiSigninRequest(data) {
  const token=(await chrome.storage.local.get('staffQueueCredential')).staffQueueCredential;
  if(!token)throw Error('Pair this desktop first.');
  const response=await fetch(osOrigin+'/api/orders-companion/signin',{
    method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
    body:JSON.stringify(data),credentials:'omit',cache:'no-store',redirect:'error',signal:AbortSignal.timeout(20000)});
  if(!response.ok)throw Error('Prodigi sign-in recovery will retry when the connection returns.');
  return response.json();
}
function prodigiSigninKind(plan){return plan.kind==='product'?'product':plan.kind==='qa'?'qa':plan.kind===undefined?'artwork':null;}
function prodigiSigninURL(orderUrl){return 'https://dashboard.prodigi.com/login?redirect='+encodeURIComponent(new URL(orderUrl).pathname);}
async function prodigiSigninNeeded(plan,error) {
  if(!prodigiSigninKind(plan)||plan.environment!=='live')return false;
  if(error?.code==='PRODIGI_SIGNIN_REQUIRED'||[
    'Prodigi image library authentication expired before image selection.',
    'Sign into Prodigi in Edge, then review the same draft.'
  ].includes(error?.message))return true;
  const saved=(await chrome.storage.local.get('ordersWorkerTabs')).ordersWorkerTabs||{};
  try{return prodigiLoginAddress((await chrome.tabs.get(saved[plan.order_url])).url,plan.order_url);}catch{return false;}
}
async function prodigiPauseForSignin(plan) {
  // Keep the original handoff as an outbox until the server acknowledges its
  // durable wait. A network failure or worker reload cannot silently drop it.
  await chrome.storage.local.set({ordersBrowserPending:{...plan,ordersSignInDetected:true}});
  const result=await prodigiSigninRequest({action:'wait',key:plan.key,token:plan.token,
    kind:prodigiSigninKind(plan),login_url:prodigiSigninURL(plan.order_url)});
  if(!['waiting','retired'].includes(result.status))throw Error('Sign-in wait was not acknowledged.');
  if(result.status==='waiting'){
    const saved=(await chrome.storage.local.get('ordersWorkerTabs')).ordersWorkerTabs||{};
    const id=saved[plan.order_url];
    if(Number.isInteger(id)){
      const current=await chrome.tabs.get(id);
      if(prodigiOrderAddress(current.pendingUrl||current.url,plan.order_url))
        await chrome.tabs.update(id,{url:prodigiSigninURL(plan.order_url)});
    }
  }
  await chrome.storage.local.remove('ordersBrowserPending');
  if(typeof continueOrdersSoon==='function')continueOrdersSoon();
  return {status:result.status==='waiting'?'Waiting for Prodigi sign-in':'Handoff unavailable'};
}
async function prodigiSigninOwnedTab(wait,replace=false) {
  const saved=(await chrome.storage.local.get('ordersWorkerTabs')).ordersWorkerTabs||{};
  const id=saved[wait.order_url];
  if(!replace&&Number.isInteger(id)){
    try{const tab=await chrome.tabs.get(id);
      if(prodigiOrderAddress(tab.url,wait.order_url)||prodigiLoginAddress(tab.url,wait.order_url))return tab;
      const current=new URL(tab.pendingUrl||tab.url);
      // Keep a supplier-hosted verification handoff open for the user. No
      // credentials or navigation are allowed on an unrecognised auth page.
      if(current.origin==='https://dashboard.prodigi.com'&&!current.pathname.startsWith('/orders/'))return tab;
    }catch{}
  }
  // Preserve closed/navigated user tabs. Only create a new worker-owned tab.
  const tab=await chrome.tabs.create({url:wait.order_url,active:false});
  await chrome.storage.local.set({ordersWorkerTabs:{...saved,[wait.order_url]:tab.id}});
  return tab;
}
async function prodigiSigninBadge(waiting) {
  if(!chrome.action)return;
  await chrome.action.setBadgeText({text:waiting?'!':''});
  await chrome.action.setTitle({title:waiting?'Prodigi sign-in needed · orders resume automatically':'Sports Cave Companion'});
  if(waiting)await chrome.action.setBadgeBackgroundColor({color:'#b45309'});
}
function prodigiSigninWaitValid(wait) {
  return wait&&/^[A-Za-z0-9_-]{32}$/.test(wait.id)&&/^prodigi_prepare:\d+$/.test(wait.key)&&
    ['artwork','product','qa'].includes(wait.kind)&&
    /^https:\/\/dashboard\.prodigi\.com\/orders\/[A-Za-z0-9-]{1,100}\/detail$/.test(wait.order_url)&&
    prodigiLoginAddress(wait.login_url,wait.order_url);
}
async function prodigiSigninRecover() {
  const state=await prodigiSigninRequest({action:'pending'});
  if(!Array.isArray(state.waits)||state.waits.length>100||state.waits.some(w=>!prodigiSigninWaitValid(w)))
    throw Error('Invalid Prodigi sign-in recovery response.');
  await prodigiSigninBadge(state.waits.length>0);
  if(!state.waits.length){
    for(const key of ['ordersSigninAlert','ordersSigninReady','ordersSigninFresh'])await chrome.storage.local.remove(key);
    return {waiting:false};
  }
  const local=await chrome.storage.local.get(['ordersSigninAlert','ordersSigninReady','ordersSigninFresh']);
  let restored=Number.isFinite(local.ordersSigninReady)&&Date.now()-local.ordersSigninReady<30000,automatic=state.automatic!==false;
  await chrome.storage.local.remove('ordersSigninReady');
  // Bounded work; an unresolved login never monopolises the Orders queue.
  for(const wait of state.waits.slice(0,8)){
    try{
      const tab=await prodigiSigninOwnedTab(wait);
      const currentUrl=tab.pendingUrl||tab.url;
      if(prodigiOrderAddress(currentUrl,wait.order_url)){
        let ready;
        try{ready=await prodigiReadyProbe(tab.id);}catch{
          // An extension update invalidates old content-script receivers. Use a
          // fresh owned context, preserving any manual editor in the old tab.
          const fresh=local.ordersSigninFresh||{};
          if(!fresh[wait.id]||Date.now()-fresh[wait.id]>300000){
            local.ordersSigninFresh={...fresh,[wait.id]:Date.now()};
            await chrome.storage.local.set({ordersSigninFresh:local.ordersSigninFresh});
            await prodigiSigninOwnedTab(wait,true);
          }
          continue;
        }
        if(!ready?.ready)continue;
        const done=await prodigiSigninRequest({action:'resume',key:wait.key,kind:wait.kind,id:wait.id});
        if(['resumed','retired','review'].includes(done.status)){
          restored=true;if(typeof continueOrdersSoon==='function')continueOrdersSoon();
        }
        continue;
      }
      if(!prodigiLoginAddress(currentUrl,wait.order_url))continue;
      if(restored){await chrome.tabs.update(tab.id,{url:wait.order_url});continue;}
      let notice;
      try{notice=await chrome.tabs.sendMessage(tab.id,{type:'prodigi:signin:notice',order_url:wait.order_url,detail:prodigiSigninDetail});}catch{}
      if(automatic&&['email','password'].includes(notice?.step)){
        automatic=false;
        let credential;
        try{
          credential=await prodigiSigninRequest({action:'credentials',key:wait.key,kind:wait.kind,id:wait.id,login_url:currentUrl});
          if(credential.available===true&&credential.username==='hello@sportscave.com.au'&&typeof credential.password==='string'&&credential.password){
            // Recheck immediately before sending to the top-frame login script.
            const current=await chrome.tabs.get(tab.id);
            if(!prodigiLoginAddress(current.url,wait.order_url))continue;
            await chrome.tabs.sendMessage(tab.id,{type:'prodigi:signin:fill',order_url:wait.order_url,
              username:credential.username,password:credential.password},{frameId:0});
          }
        }finally{if(credential){credential.password='';credential=null;}}
        if(typeof continueOrdersSoon==='function')continueOrdersSoon(1000);
      }
      const incident=state.incident||state.waits[0].id;
      if(local.ordersSigninAlert!==incident){
        // One visible alert per incident, restored after a worker restart.
        await chrome.tabs.update(tab.id,{active:true,autoDiscardable:false});
        await chrome.storage.local.set({ordersSigninAlert:incident});local.ordersSigninAlert=incident;
      }
    }catch{
      // Lost login tab, MFA, credential denial or an outage leaves the durable
      // wait intact. Another order remains free to run on this same tick.
    }
  }
  return {waiting:true};
}
async function prodigiSigninHandoff(plan,tab,message){
  let timer;const deadline=Date.now()+900000;
  const signedOut=new Promise((_,reject)=>{timer=setInterval(()=>{
    void chrome.storage.local.get('ordersWorkerTabs').then(async state=>{
      if(state.ordersWorkerTabs?.[plan.order_url]!==tab.id){reject(Error('The worker order tab changed during the supplier action.'));return;}
      const current=await chrome.tabs.get(tab.id);
      if(prodigiLoginAddress(current.pendingUrl||current.url,plan.order_url))reject(prodigiSignInRequired());
      else if(!prodigiOrderAddress(current.pendingUrl||current.url,plan.order_url)||Date.now()>deadline)
        reject(Error('The supplier browser response was interrupted. Verify the saved order before continuing.'));
    }).catch(()=>reject(Error('The supplier order tab closed. Verify its saved state before continuing.')));
  },1000);});
  try{return await Promise.race([chrome.tabs.sendMessage(tab.id,message,{frameId:0}),signedOut]);}
  finally{clearInterval(timer);}
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  if(message?.type!=='prodigi:signin:ready'||sender.id!==chrome.runtime.id||sender.frameId!==0||
    !/^https:\/\/dashboard\.prodigi\.com\/orders\/[A-Za-z0-9-]{1,100}\/detail$/.test(sender.url||''))return;
  // Readiness is a wake hint only. It grants no permit or QA evidence.
  chrome.storage.local.set({ordersSigninReady:Date.now()}).then(()=>{if(typeof continueOrdersSoon==='function')continueOrdersSoon();reply({received:true});});
  return true;
});
