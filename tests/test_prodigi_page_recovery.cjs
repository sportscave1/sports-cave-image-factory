'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(require.resolve('../windows-upload-companion/prodigi-browser.js'),'utf8');
const url='https://dashboard.prodigi.com/orders/99/detail';
function setup(oldState='frozen',freshReady=true){
 const events=[],listeners=[],storage={ordersWorkerTabs:{[url]:9}};
 const context=vm.createContext({URL,Date,setTimeout:(fn,ms)=>setTimeout(fn,ms===1500?2:0),clearTimeout,
  chrome:{storage:{local:{get:async()=>storage,set:async v=>Object.assign(storage,v)}},
   runtime:{onMessage:{addListener:f=>listeners.push(f)}},tabs:{
    get:async id=>({id,url}),
    update:async(id,options)=>{events.push({action:'wake',id,options});return{id,url};},
    reload:async()=>assert.fail('An unidentified old document must be preserved'),
    create:async options=>{events.push({action:'create',options});return{id:10,url};},
    sendMessage:async(id,message)=>{
     assert.equal(message.type,'prodigi:ready','No supplier action during readiness recovery');
     if(id===10)return{ready:freshReady,page_instance:'fresh-document'};
     if(oldState==='missing')throw Error('Could not establish connection. Receiving end does not exist.');
     if(oldState==='unidentified')return{ready:true};
     return new Promise(()=>{});
    }}}});
 vm.runInContext(source,context);
 context.plan={kind:'qa',fresh_saved_order:true,order_url:url};
 context.tab={id:9,url,ordersReused:true};
 return{context,events,storage,listeners};
}

for(const state of ['frozen','missing','unidentified'])test('fresh owned page recovers '+state+' previous document without reloading it',async()=>{
 const {context,events,storage}=setup(state);
 const result=await vm.runInContext('prodigiReadyOwnedPage(plan,tab,true,3)',context);
 assert.equal(result.id,10);assert.equal(storage.ordersWorkerTabs[url],10);
 assert.equal(events.filter(e=>e.action==='create').length,1);
 assert.equal(events.find(e=>e.action==='create').options.url,url);
 assert.equal(events.find(e=>e.action==='create').options.active,true);
 assert(events.filter(e=>e.action==='wake').length<=1);
});

test('a fresh page that also stalls creates no tab loop or supplier action',async()=>{
 const {context,events}=setup('frozen',false);
 assert.equal(await vm.runInContext('prodigiReadyOwnedPage(plan,tab,true,3)',context),null);
 assert.equal(events.filter(e=>e.action==='create').length,1);
});

for(const change of ['mapping','destination','signin'])test('document recovery stops when '+change+' changes',async()=>{
 const {context,events,storage}=setup();
 if(change==='mapping')storage.ordersWorkerTabs[url]=11;
 if(change==='destination')context.chrome.tabs.get=async id=>({id,url:url.replace('/99/','/100/')});
 if(change==='signin')context.chrome.tabs.get=async id=>({id,url:'https://dashboard.prodigi.com/login?redirect='+encodeURIComponent('/orders/99/detail')});
 await assert.rejects(vm.runInContext('prodigiReadyOwnedPage(plan,tab,true,3)',context));
 assert.equal(events.length,0);
});

test('an ordinary unapproved editor cannot use missing-identity recovery',async()=>{
 const {context,events}=setup();context.plan={order_url:url};
 assert.equal(await vm.runInContext('prodigiReadyOwnedPage(plan,tab,true,3)',context),null);
 assert.equal(events.filter(e=>e.action==='create').length,0);
});

test('ownership changing immediately before replacement cannot be claimed',async()=>{
 const {context,events,storage}=setup();
 vm.runInContext('prodigiWaitForPage=async()=>false',context);
 storage.ordersWorkerTabs[url]=11;
 await assert.rejects(vm.runInContext('prodigiReadyOwnedPage(plan,tab,true,3)',context));
 assert.equal(events.length,0);
});

for(const change of ['mapping','destination','signin'])test('responsive old page cannot refresh after '+change+' changes',async()=>{
 const {context,events,storage}=setup();let reads=0;
 context.chrome.tabs.get=async id=>{
  if(++reads===2){
   if(change==='mapping')storage.ordersWorkerTabs[url]=11;
   if(change==='destination')return{id,url:url.replace('/99/','/100/')};
   if(change==='signin')return{id,url:'https://dashboard.prodigi.com/login?redirect='+encodeURIComponent('/orders/99/detail')};
  }
  return{id,url};
 };
 context.chrome.tabs.sendMessage=async()=>({ready:true,page_instance:'old-document'});
 await assert.rejects(vm.runInContext('prodigiReadyOwnedPage(plan,tab,true,3)',context));
 assert.equal(events.length,0);
});

test('recovered empty-item upload transfers only to the new tab and requests one Save permit',async()=>{
 const {context,storage,listeners}=setup(),calls=[];let uploads=0;
 const data=new TextEncoder().encode('exact');
 const plan={environment:'live',order_id:'99',item_id:'88',order_url:url,key:'prodigi_prepare:1',token:'a'.repeat(43),
  reference:'synthetic',exact_item:true,fresh_empty_item:true,bytes:data.length,
  filename:'SC-1-'+'a'.repeat(16)+'-'+'b'.repeat(8)+'.jpg',
  artwork_url:'https://sports-cave-image-factory.onrender.com/api/prodigi-artwork/'+'a'.repeat(43),
  sha256:require('node:crypto').createHash('sha256').update(data).digest('hex')};
 Object.assign(context,{plan,crypto:require('node:crypto').webcrypto,Uint8Array,AbortSignal,
  osOrigin:'https://sports-cave-image-factory.onrender.com',btoa:s=>Buffer.from(s,'binary').toString('base64'),
  fetch:async(address,options)=>{
   calls.push(address);
   if(address===plan.artwork_url)return{ok:true,headers:{get:()=>null},arrayBuffer:async()=>data.buffer};
   assert(address.startsWith(context.osOrigin+'/api/orders-companion/browser/'));
   assert.equal(JSON.parse(options.body).token,plan.token);
   return{ok:true,json:async()=>address.endsWith('/permit')?{permitted:true}:{status:'Checking QA'}};
  }});
 storage.staffQueueCredential='paired';context.chrome.storage.local.remove=async k=>delete storage[k];
 const probe=context.chrome.tabs.sendMessage;
 context.chrome.tabs.sendMessage=async(id,message)=>{
  if(message.type==='prodigi:ready')return probe(id,message);
  assert.equal(message.type,'prodigi:upload');assert.equal(id,10);uploads++;
  const sender={frameId:0,tab:{id},url};
  listeners[0]({type:'prodigi:chunk',offset:0},{...sender,tab:{id:9}},()=>assert.fail('Old tab cannot read transferred artwork'));
  let chunk;listeners[0]({type:'prodigi:chunk',offset:0},sender,result=>chunk=result);
  assert.equal(Buffer.from(chunk.base64,'base64').toString(),'exact');
  const permission=await new Promise(resolve=>listeners[0]({type:'prodigi:permit',sha256:plan.sha256},sender,resolve));
  assert.equal(permission.permitted,true);
  return{saved:true,stage:'save'};
 };
 assert.equal((await vm.runInContext('prodigiBrowserRun(plan)',context)).status,'Checking QA');
 assert.equal(uploads,1);assert.equal(calls.filter(a=>a.endsWith('/permit')).length,1);
 assert.equal(calls.filter(a=>a.endsWith('/finish')).length,1);assert.equal(calls.filter(a=>a===plan.artwork_url).length,1);
 assert.equal(storage.ordersBrowserPending,undefined);
});
