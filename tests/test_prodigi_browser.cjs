'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const {webcrypto}=require('node:crypto');
const source=fs.readFileSync(require('node:path').join(__dirname,'../windows-upload-companion/prodigi-browser.js'),'utf8');
const {prodigiExactRow}=require('../windows-upload-companion/prodigi-page.js');
test('the supplier row matches exact SKU elements even when the row text is concatenated',()=>{
  function row(sku,colour) {
    const code={textContent:sku},frame={textContent:colour};
    return{textContent:'UploadProduct(A2)'+sku+'Frame colour:'+colour+'Changex1qty',
      querySelectorAll:selector=>selector==='strong'?[frame]:[code,frame]};
  }
  assert(prodigiExactRow(row('GLOBAL-CFP-A2','Natural'),'GLOBAL-CFP-A2','natural'));
  assert(!prodigiExactRow(row('GLOBAL-CFP-A2-BACKLOADER','Natural'),'GLOBAL-CFP-A2','natural'));
  assert(!prodigiExactRow(row('GLOBAL-CFP-A2','Black'),'GLOBAL-CFP-A2','natural'));
});
const plan={environment:'sandbox',order_id:'99',item_id:'88',key:'fixture',token:'fixture',reference:'SC-SANDBOX-fixture',
  order_url:'https://sandbox-beta-dashboard.pwinty.com/orders/99/detail',
  artwork_url:'https://sports-cave-image-factory.onrender.com/api/prodigi-artwork/'+'a'.repeat(43),
  sha256:require('node:crypto').createHash('sha256').update('exact').digest('hex'),bytes:5,filename:'SC-1-'+'a'.repeat(16)+'-'+'b'.repeat(8)+'.jpg'};
function setup(bytes='exact',saved=true) {
  const calls=[],tabs=[],listeners=[],storage={staffQueueCredential:'paired'};
  const chrome={storage:{local:{get:async()=>storage,set:async v=>Object.assign(storage,v),remove:async k=>delete storage[k]}},
    runtime:{onMessage:{addListener:f=>listeners.push(f)}},
    tabs:{create:async p=>{tabs.push(p);return{id:9};},sendMessage:async(id,m)=>m.type==='prodigi:ready'?{ready:true}:{saved}}};
  const context=vm.createContext({chrome,fetch:async(url,options)=>{
    calls.push({url,options});
    if(url===plan.artwork_url)return {ok:true,headers:{get:()=>null},arrayBuffer:async()=>new TextEncoder().encode(bytes).buffer};
    return{ok:true,json:async()=>({status:'Needs QA'})};
  },crypto:webcrypto,Uint8Array,AbortSignal,URL,Date,setTimeout,btoa:s=>Buffer.from(s,'binary').toString('base64'),
    osOrigin:'https://sports-cave-image-factory.onrender.com'});
  vm.runInContext(source,context);
  return{context,calls,tabs,storage,listeners};
}
test('only exact pinned artwork and supplier order destinations are accepted',()=>{
  const {context}=setup();context.plan=plan;
  assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),true);
  for(const change of [{order_url:'https://dashboard.prodigi.com/login'},
    {artwork_url:'https://other.example/file.jpg'},{bytes:200*1024*1024},{environment:'other'}]) {
    context.plan={...plan,...change};assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),false);
  }
});
test('the image library may add its own filters without changing the pinned order',()=>{
  const {context}=setup();context.expected=plan.order_url;
  context.address=plan.order_url+'?imageLibraryType=artwork%2Cbook&imageLibraryFileType=png%2Cjpg';
  assert.equal(vm.runInContext('prodigiOrderAddress(address,expected)',context),true);
  for(const address of [plan.order_url.replace('/99/','/100/'),
    plan.order_url.replace('sandbox-beta-dashboard.pwinty.com','dashboard.prodigi.com'),
    plan.order_url+'?redirect=elsewhere',plan.order_url+'#other']) {
    context.address=address;assert.equal(vm.runInContext('prodigiOrderAddress(address,expected)',context),false);
  }
});
test('worker uploads only verified bytes and opens the exact draft without activation',async()=>{
  const {context,calls,tabs,storage}=setup();context.plan=plan;
  const result=await vm.runInContext('prodigiBrowserRun(plan)',context);
  assert.equal(result.status,'Needs QA');assert.equal(tabs.length,1);
  assert.equal(tabs[0].url,plan.order_url);assert.equal(tabs[0].active,false);
  assert.equal(calls.length,2);assert(calls.every(c=>c.url.startsWith('https://sports-cave-image-factory.onrender.com/')));
  assert(!storage.ordersBrowserPending);
});
test('checksum mismatch never opens or uploads to a supplier tab',async()=>{
  const {context,tabs,calls}=setup('wrong');context.plan=plan;
  await vm.runInContext('prodigiBrowserRun(plan)',context);
  assert.equal(tabs.length,0);assert.equal(calls.length,2);
  assert(calls[1].url.endsWith('/finish'));
});
test('uncertain Save is reconciled once without another upload',async()=>{
  const {context,tabs,calls}=setup('exact',false);context.plan=plan;
  await vm.runInContext('prodigiBrowserRun(plan)',context);
  assert.equal(tabs.length,1);assert.equal(calls.filter(c=>c.url.endsWith('/finish')).length,1);
});
