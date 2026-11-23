'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const read=name=>fs.readFileSync(path.join(__dirname,'../windows-upload-companion/',name),'utf8');
const order='https://dashboard.prodigi.com/orders/99/detail';
const login='https://dashboard.prodigi.com/login?redirect=%2Forders%2F99%2Fdetail';
const wait={key:'prodigi_prepare:1',kind:'product',id:'w'.repeat(32),order_url:order,login_url:login,mode:'unused'};
const plan={kind:'product',environment:'live',order_id:'99',item_id:'88',order_url:order,key:'product:prodigi_prepare:1',
 token:'a'.repeat(43),sha256:'b'.repeat(64),sku:'GLOBAL-CFP-A2',colour:'Natural',reference:'#SC1'};
function worker(url=login){
 const saved={staffQueueCredential:'p'.repeat(43),ordersWorkerTabs:{[order]:9}},calls=[],actions=[],listeners=[];
 const tabs=new Map([[9,{id:9,url}]]);let next=10;
 const state={waits:[{...wait}],automatic:true,incident:'incident'};
 const chrome={storage:{local:{get:async()=>saved,set:async value=>Object.assign(saved,value),remove:async key=>{delete saved[key];}}},
  runtime:{id:'extension',onMessage:{addListener:fn=>listeners.push(fn)},onStartup:{addListener(){}},onInstalled:{addListener(){}}},
  action:{setBadgeText:async v=>actions.push(['badge',v.text]),setTitle:async()=>{},setBadgeBackgroundColor:async()=>{}},
  alarms:{get:async()=>({}),create:async()=>{},onAlarm:{addListener(){}}},
  tabs:{get:async id=>{if(!tabs.has(id))throw Error('closed');return {...tabs.get(id)};},
   create:async options=>{const tab={id:next++,url:options.url};tabs.set(tab.id,tab);actions.push(['create',options.url]);return tab;},
   update:async(id,options)=>{actions.push(['update',id,options]);if(options.url)tabs.get(id).url=options.url;return tabs.get(id);},
   reload:async()=>assert.fail('No reload during sign-in'),
   sendMessage:async(id,message,options)=>{actions.push(['message',id,message.type]);
    if(message.type==='prodigi:ready')return {ready:true};
    if(message.type==='prodigi:signin:notice')return {step:'email'};
    if(message.type==='prodigi:signin:fill'){assert.equal(options.frameId,0);assert.equal(message.password,'synthetic-password-only');return {submitted:true};}
    throw Error('Unexpected supplier message');}}};
 const context=vm.createContext({chrome,URL,AbortSignal,Date,setTimeout,clearTimeout,setInterval,clearInterval,
  osOrigin:'https://sports-cave-image-factory.onrender.com',
  fetch:async(url,options)=>{const data=JSON.parse(options.body);calls.push({url,data});
   if(data.action==='pending')return {ok:true,json:async()=>({...state,waits:state.waits.map(w=>({...w}))})};
   if(data.action==='credentials'){state.automatic=false;return {ok:true,json:async()=>({available:true,username:'hello@sportscave.com.au',password:'synthetic-password-only'})};}
   if(data.action==='wait')return {ok:true,json:async()=>({status:'waiting',wait})};
   if(data.action==='resume'){state.waits=state.waits.filter(w=>w.id!==data.id);return {ok:true,json:async()=>({status:'resumed'})};}
   return {ok:true,json:async()=>({enabled:true,job:null,browser:null})};}});
 vm.runInContext(read('prodigi-browser.js'),context);vm.runInContext(read('prodigi-signin.js'),context);
 context.plan={...plan};return {context,saved,calls,actions,tabs,state,listeners,chrome};
}
test('expired authentication becomes a durable wait without finishing or clicking the supplier',async()=>{
 const w=worker();const result=await vm.runInContext('prodigiBrowserRun(plan)',w.context);
 assert.equal(result.status,'Waiting for Prodigi sign-in');assert(!w.saved.ordersBrowserPending);
 assert.deepEqual(w.calls.map(c=>c.data.action),['wait']);
 assert(!w.actions.some(a=>a[0]==='message'));
});
test('library JWT expiry navigates only the owned exact order to pinned login',async()=>{
 const w=worker(order);
 assert.equal(await vm.runInContext("prodigiSigninNeeded(plan,Error('Prodigi image library authentication expired before image selection.'))",w.context),true);
 await vm.runInContext('prodigiPauseForSignin(plan)',w.context);
 assert.equal(w.tabs.get(9).url,login);
 assert.deepEqual(w.actions.filter(a=>a[0]==='update').map(a=>a[1]),[9]);
});
test('failed wait acknowledgement retains the sign-in outbox over worker restart',async()=>{
 const w=worker();w.context.fetch=async()=>{throw Error('offline');};
 await assert.rejects(vm.runInContext('prodigiBrowserRun(plan)',w.context),/offline/);
 assert.equal(w.saved.ordersBrowserPending.ordersSignInDetected,true);
 assert.equal(w.saved.ordersBrowserPending.token,plan.token);
});
test('saved password enters only the top-frame pinned login and is absent from persistent state and requests',async()=>{
 const w=worker();await vm.runInContext('prodigiSigninRecover()',w.context);
 assert.deepEqual(w.calls.map(c=>c.data.action),['pending','credentials']);
 assert.equal(w.actions.filter(a=>a[2]==='prodigi:signin:fill').length,1);
 assert(!JSON.stringify(w.saved).includes('synthetic-password-only'));
 assert(!JSON.stringify(w.calls).includes('synthetic-password-only'));
 await vm.runInContext('prodigiSigninRecover()',w.context);
 assert.equal(w.calls.filter(c=>c.data.action==='credentials').length,1);
 assert.equal(w.actions.filter(a=>a[0]==='update'&&a[2].active).length,1);
});
test('a redirect changed during credential retrieval receives no password',async()=>{
 const w=worker(),fetch=w.context.fetch;
 w.context.fetch=async(url,opts)=>{const result=await fetch(url,opts);if(JSON.parse(opts.body).action==='credentials')w.tabs.get(9).url='https://evil.example/login';return result;};
 await vm.runInContext('prodigiSigninRecover()',w.context);
 assert(!w.actions.some(a=>a[2]==='prodigi:signin:fill'));
});
test('manual sign-in resumes the original wait and clears the alert on the next poll',async()=>{
 const w=worker(order);await vm.runInContext('prodigiSigninRecover()',w.context);
 assert.deepEqual(w.calls.map(c=>c.data.action),['pending','resume']);
 assert.equal(w.calls[1].data.id,wait.id);
 await vm.runInContext('prodigiSigninRecover()',w.context);
 assert(!w.saved.ordersSigninAlert);assert(w.actions.some(a=>a[0]==='badge'&&a[1]===''));
});
test('a ready signed-in page wakes sibling login tabs without issuing supplier authority',async()=>{
 const w=worker();w.saved.ordersSigninReady=Date.now();
 await vm.runInContext('prodigiSigninRecover()',w.context);
 assert.equal(w.tabs.get(9).url,order);assert.deepEqual(w.calls.map(c=>c.data.action),['pending']);
});
test('foreign and closed tabs are preserved while a fresh worker-owned order tab recovers',async()=>{
 for(const closed of [false,true]){
  const w=worker('https://example.invalid/user-page');if(closed)w.tabs.delete(9);
  await vm.runInContext('prodigiSigninRecover()',w.context);
  assert.equal(w.saved.ordersWorkerTabs[order],10);
  if(!closed)assert.equal(w.tabs.get(9).url,'https://example.invalid/user-page');
  assert(w.actions.some(a=>a[0]==='create'&&a[1]===order));
 }
});
test('pending navigation to login is never mistaken for completed sign-in',async()=>{
 const w=worker(order);w.tabs.get(9).pendingUrl=login;
 await vm.runInContext('prodigiSigninRecover()',w.context);
 assert(!w.calls.some(c=>c.data.action==='resume'));
});
test('extension reload restores a missing order receiver using a fresh owned tab',async()=>{
 const w=worker(order);w.chrome.tabs.sendMessage=async()=>{throw Error('Receiving end does not exist');};
 await vm.runInContext('prodigiSigninRecover()',w.context);
 assert(w.actions.some(a=>a[0]==='create'&&a[1]===order));
 assert.equal(w.tabs.get(9).url,order);assert.equal(w.saved.ordersWorkerTabs[order],10);
});
test('authentication loss breaks a hung supplier message without another supplier action',async()=>{
 const w=worker(order);w.chrome.tabs.sendMessage=async()=>new Promise(()=>{});
 w.context.tab={id:9};const pending=vm.runInContext("prodigiSigninHandoff(plan,tab,{type:'prodigi:product'})",w.context);
 w.tabs.get(9).url=login;
 await assert.rejects(pending,e=>e.code==='PRODIGI_SIGNIN_REQUIRED');
 assert(!w.actions.some(a=>a[0]==='create'||a[0]==='update'));
});
test('a supplier verification page is preserved for manual completion without another login tab',async()=>{
 const w=worker('https://dashboard.prodigi.com/login/verification');
 await vm.runInContext('prodigiSigninRecover()',w.context);
 assert(!w.actions.some(a=>a[0]==='create'||a[0]==='update'||a[0]==='message'));
 assert.deepEqual(w.calls.map(c=>c.data.action),['pending']);
});
test('malformed destinations stop before tabs or credentials are touched',async()=>{
 const w=worker();w.state.waits[0].order_url='https://evil.example/orders/99/detail';
 await assert.rejects(vm.runInContext('prodigiSigninRecover()',w.context),/Invalid Prodigi/);
 assert.equal(w.actions.length,0);assert.equal(w.calls.length,1);
});
test('a sign-in service outage does not cancel an independent Orders tick',async()=>{
 const w=worker();w.context.prodigiSigninRecover=async()=>{throw Error('unavailable');};
 vm.runInContext(read('orders-queue.js'),w.context);
 assert.equal(await vm.runInContext('ordersQueueTick()',w.context),true);
 assert(w.calls.some(c=>c.url.endsWith('/tick')));
});
test('a pending login allows preparation polls while deferring additional supplier browser claims',async()=>{
 const w=worker();w.context.prodigiSigninRecover=async()=>({waiting:true});
 const original=w.context.fetch;let header;
 w.context.fetch=async(url,options)=>{if(url.endsWith('/tick'))header=options.headers['X-Sports-Cave-Orders-Signin-Waiting'];return original(url,options);};
 vm.runInContext(read('orders-queue.js'),w.context);
 assert.equal(await vm.runInContext('ordersQueueTick()',w.context),true);assert.equal(header,'1');
});
test('reload drains a sign-in outbox through pause, never an interrupted finish',async()=>{
 const w=worker();w.saved.ordersBrowserPending={...plan,ordersSignInDetected:true};
 w.context.prodigiSigninRecover=async()=>{};w.context.prodigiPauseForSignin=async()=>{delete w.saved.ordersBrowserPending;return{status:'Waiting for Prodigi sign-in'};};
 w.context.prodigiResumeCompletion=async()=>assert.fail('No finish for a waiting login');
 vm.runInContext(read('orders-queue.js'),w.context);
 assert.equal(await vm.runInContext('ordersQueueTick()',w.context),true);
 assert(!w.saved.ordersBrowserPending);
});
function page({step='email',account='hello@sportscave.com.au',url=login,manualPassword='',formAction=null,duplicate=false,mfa=false}={}){
 const actions=[],listeners=[];let phase=step;
 class Input {constructor(type){this.type=type;this.id=type;this.name=type;this._value=type==='password'?manualPassword:'';this.disabled=false;this.form=form;}
  get value(){return this._value;}set value(v){this._value=v;}getClientRects(){return [{}];}dispatchEvent(){} }
 const button={disabled:false,textContent:'Continue',getClientRects:()=>[{}],click(){actions.push(phase);phase=phase==='email'?'password':'submitted';}};
 const form={target:'',getAttribute:()=>formAction,querySelectorAll:()=>[button]};
 const inputEmail=new Input('email'),inputPassword=new Input('password');
 const main={get innerText(){return mfa?'Enter verification code':phase==='email'?'Log in or register':`Welcome back, Nathan! ${account}`;},
  querySelectorAll(selector){if(selector==='input'){const field=phase==='email'?inputEmail:inputPassword;return duplicate?[field,field]:[field];}
   if(selector==='[title]')return [{getAttribute:()=>account}];return [];} };
 const banner={style:{},setAttribute(){}};
 const window={};window.top=window;
 const context=vm.createContext({window,URL,location:new URL(url),HTMLInputElement:Input,Event:class{},Date,
  setTimeout:fn=>{queueMicrotask(fn);return 1;},setInterval:()=>1,clearInterval(){},
  document:{querySelector:selector=>selector==='main'?main:null,getElementById:()=>null,createElement:()=>banner,body:{appendChild(){}}},
  chrome:{runtime:{id:'extension',onMessage:{addListener:fn=>listeners.push(fn)},sendMessage:async()=>{}}}});
 vm.runInContext(read('prodigi-signin-page.js'),context);
 const invoke=message=>new Promise(resolve=>{const keep=listeners[0](message,{id:'extension'},resolve);if(!keep)resolve(undefined);});
 const fill=()=>invoke({type:'prodigi:signin:fill',order_url:order,username:'hello@sportscave.com.au',password:'synthetic-password-only'});
 return {fill,invoke,actions,inputEmail,inputPassword,banner};
}
test('actual two-step Prodigi form uses the saved email then password exactly once',async()=>{
 const p=page();assert.equal((await p.fill()).submitted,true);
 assert.deepEqual(p.actions,['email','password']);assert.equal(p.inputEmail.value,'hello@sportscave.com.au');
 assert.equal((await p.fill()).submitted,false);assert.deepEqual(p.actions,['email','password']);
});
for(const options of [{step:'password',account:'other@example.invalid'},{mfa:true},{duplicate:true},{formAction:'https://evil.example/login'},
 {formAction:'/register'},{url:login+'&redirect=%2Forders%2Fother%2Fdetail'},{step:'password',manualPassword:'typed-by-user'}])
 test('changed/manual login form never receives or submits saved password: '+JSON.stringify(options),async()=>{
  const p=page(options);await p.fill();assert.deepEqual(p.actions,[]);
  assert.equal(p.inputPassword.value,options.manualPassword||'');
 });
test('password step for the exact existing account is supported without another email submit',async()=>{
 const p=page({step:'password'});assert.equal((await p.fill()).submitted,true);assert.deepEqual(p.actions,['password']);
});
