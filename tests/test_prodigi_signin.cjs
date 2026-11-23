const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync(require('node:path').join(__dirname,'../windows-upload-companion/prodigi-browser.js'),'utf8');
const order='https://dashboard.prodigi.com/orders/75351351495771648/detail';
const login='https://dashboard.prodigi.com/login?redirect='+encodeURIComponent(new URL(order).pathname);
function setup(url=login){
 const actions=[];const saved={ordersWorkerTabs:{[order]:9}};
 const context=vm.createContext({URL,setTimeout,clearTimeout,chrome:{
  storage:{local:{get:async()=>saved,set:async v=>Object.assign(saved,v)}},
  runtime:{onMessage:{addListener(){}}},tabs:{get:async id=>({id,url}),
  create:async()=>{actions.push('create');return{id:10}},update:async()=>actions.push('update'),
  reload:async()=>actions.push('reload'),sendMessage:async()=>{actions.push('probe');return{ready:true,page_instance:'page'}}}}});
 vm.runInContext(source,context);context.order=order;context.plan={order_url:order};context.tab={id:9,url:order,ordersReused:true};
 return {context,actions,saved};
}
test('expired sign-in is reported before probing, reloading or duplicating an owned tab',async()=>{
 for(const expression of ['prodigiWorkerTab(plan)','prodigiWorkerTab(plan,true)','prodigiWaitForPage(tab,false,1,order)','prodigiWaitForPage(tab,true,1,order)','prodigiWakeOwnedTab(tab,order)']){
  const {context,actions}=setup();
  await assert.rejects(vm.runInContext(expression,context),e=>e.code==='PRODIGI_SIGNIN_REQUIRED'&&e.prodigiStage==='signin');
  assert.deepEqual(actions,[]);
 }
});
test('login redirects require exact origin, exact order and unambiguous redirect',()=>{
 const {context}=setup();context.login=login;
 assert.equal(vm.runInContext('prodigiLoginAddress(login,order)',context),true);
 for(const bad of [login.replace('dashboard.prodigi.com','evil.example'),login+'&redirect=%2Forders%2Fother%2Fdetail',login+'&next=elsewhere',login+'#x',login.replace('75351351495771648','other'),'https://dashboard.prodigi.com/login?redirect=https://evil.example']){
  context.bad=bad;assert.equal(vm.runInContext('prodigiLoginAddress(bad,order)',context),false);
 }
});
test('sign-in completion reuses the same owned exact draft without creating another tab',async()=>{
 const {context,actions}=setup(order);
 const tab=await vm.runInContext('prodigiWorkerTab(plan)',context);assert.equal(tab.id,9);
 assert.equal(await vm.runInContext('prodigiWaitForPage(tab,false,1,order)',context),true);
 assert.deepEqual(actions,['probe']);
});
test('another order is still rejected as lost ownership',async()=>{
 const {context,actions}=setup(order.replace('75351351495771648','other'));
 await assert.rejects(vm.runInContext('prodigiWakeOwnedTab(tab,order)',context),/changed before wake/);
 assert.deepEqual(actions,[]);
});
test('a login page in an unowned tab cannot grant supplier authority',async()=>{
 const {context,actions,saved}=setup();saved.ordersWorkerTabs={};
 await assert.rejects(vm.runInContext('prodigiWakeOwnedTab(tab,order)',context),/changed before wake/);
 assert.deepEqual(actions,[]);
});

test('product handoff reports sign-in stage through the durable receipt without a supplier click',async()=>{
 const {context,actions,saved}=setup();saved.staffQueueCredential='paired';
 const calls=[];context.AbortSignal=AbortSignal;context.osOrigin='https://sports-cave-image-factory.onrender.com';
 context.fetch=async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return{ok:true,json:async()=>({status:'Needs review'})};};
 context.plan={kind:'product',environment:'live',order_id:'75351351495771648',item_id:'item',
  order_url:order,key:'product:prodigi_prepare:977',token:'a'.repeat(43),sha256:'b'.repeat(64),
  sku:'GLOBAL-CFP-A3',colour:'Black',reference:'#SC3542'};
 context.chrome.storage.local.remove=async key=>delete saved[key];
 const result=await vm.runInContext('prodigiBrowserRun(plan)',context);
 assert.equal(result.status,'Needs review');assert.deepEqual(actions,[]);
 assert.equal(calls.length,1);assert.equal(calls[0].body.stage,'signin');
 assert.match(calls[0].body.error,/sign-in expired/);assert(!saved.ordersBrowserPending);
});
