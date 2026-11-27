const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../windows-upload-companion/prodigi-browser.js'),'utf8');
const url='https://dashboard.prodigi.com/orders/123/detail';
function setup(){
 const storage={ordersWorkerTabs:{[url]:9}}, events=[];
 const context=vm.createContext({URL,setTimeout,clearTimeout,chrome:{runtime:{onMessage:{addListener(){}}},
 storage:{local:{async get(){return structuredClone(storage)},async set(value){Object.assign(storage,value)}}},
 tabs:{async get(id){return {id,url:'https://dashboard.prodigi.com/orders/other/detail'}},
 async create(options){events.push(options);return {id:10,url:options.url}},
 async update(){assert.fail('Preserved tab must never be navigated or activated')},
 async sendMessage(){return {ready:false}}}}});
 vm.runInContext(source,context);
 context.plan={kind:'product',order_url:url};context.old={id:9,ordersReused:true};
 return {context,storage,events};
}
test('navigated owned product tab gets one fresh exact context; original is untouched',async()=>{
 const {context,events,storage}=setup();
 vm.runInContext(`prodigiWaitForPage=async tab=>{if(tab.id===9)throw Object.assign(Error('changed'),{prodigiOwnershipLost:true});return true}`,context);
 const tab=await vm.runInContext('prodigiReadyOwnedPage(plan,old,false,1)',context);
 assert.equal(tab.id,10);assert.equal(storage.ordersWorkerTabs[url],10);
 assert.equal(events.length,1);assert.equal(events[0].url,url);
});
test('ordinary unsaved artwork never gets fresh-context recovery',async()=>{
 const {context,events}=setup();context.plan={order_url:url};
 vm.runInContext(`prodigiWaitForPage=async()=>{throw Object.assign(Error('changed'),{prodigiOwnershipLost:true})}`,context);
 await assert.rejects(vm.runInContext('prodigiReadyOwnedPage(plan,old,false,1)',context),/changed/);
 assert.equal(events.length,0);
});
test('changed ownership still blocks replacement',async()=>{
 const {context,storage,events}=setup();storage.ordersWorkerTabs[url]=11;
 vm.runInContext(`prodigiWaitForPage=async()=>{throw Object.assign(Error('changed'),{prodigiOwnershipLost:true})}`,context);
 await assert.rejects(vm.runInContext('prodigiReadyOwnedPage(plan,old,false,1)',context),/ownership changed/);
 assert.equal(events.length,0);
});
test('sign-in stays paused and cannot be bypassed with another context',async()=>{
 const {context,events}=setup();
 vm.runInContext(`prodigiWaitForPage=async()=>{throw Object.assign(Error('sign-in'),{prodigiOwnershipLost:true,code:'PRODIGI_SIGNIN_REQUIRED'})}`,context);
 await assert.rejects(vm.runInContext('prodigiReadyOwnedPage(plan,old,false,1)',context),/sign-in/);
 assert.equal(events.length,0);
});
test('new context cannot loop if it also fails',async()=>{
 const {context,events}=setup();vm.runInContext('prodigiWaitForPage=async()=>false',context);
 context.chrome.tabs.get=async id=>({id,url});
 assert.equal(await vm.runInContext('prodigiReadyOwnedPage(plan,old,false,1)',context),null);
 assert.equal(events.length,1);
});
test('unrelated worker-tab entries created during navigation are preserved',async()=>{
 const {context,storage}=setup();
 context.chrome.tabs.create=async options=>{storage.ordersWorkerTabs['https://dashboard.prodigi.com/orders/456/detail']=22;return{id:10,url:options.url}};
 context.plan= {order_url:url};delete storage.ordersWorkerTabs[url];
 await vm.runInContext('prodigiWorkerTab(plan)',context);
 assert.equal(storage.ordersWorkerTabs['https://dashboard.prodigi.com/orders/456/detail'],22);
 assert.equal(storage.ordersWorkerTabs[url],10);
});

test('ownership change while creating recovery cannot overwrite the newer owner',async()=>{
 const {context,storage}=setup();context.chrome.tabs.get=async id=>({id,url});
 context.chrome.tabs.create=async options=>{storage.ordersWorkerTabs[url]=12;return{id:10,url:options.url}};
 await assert.rejects(vm.runInContext('prodigiWorkerTab(plan,true,9)',context),/ownership changed while opening/);
 assert.equal(storage.ordersWorkerTabs[url],12);
});

test('first owned page can recover a changed URL once before any supplier action',async()=>{
 const {context,events}=setup();context.old.ordersReused=false;
 vm.runInContext(`prodigiWaitForPage=async tab=>{if(tab.id===9)throw Object.assign(Error('changed'),{prodigiOwnershipLost:true});return true}`,context);
 const tab=await vm.runInContext('prodigiReadyOwnedPage(plan,old,false,1)',context);
 assert.equal(tab.id,10);assert.equal(events.length,1);
});
