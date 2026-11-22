'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const {webcrypto}=require('node:crypto');
const source=fs.readFileSync(require('node:path').join(__dirname,'../windows-upload-companion/prodigi-browser.js'),'utf8');
const {prodigiExactRow,prodigiControls,prodigiFilePicker}=require('../windows-upload-companion/prodigi-page.js');
const {prodigiRemovePoint}=require('../windows-upload-companion/prodigi-page.js');
const {prodigiResetControl}=require('../windows-upload-companion/prodigi-page.js');

test('Reset waits for the late SKU, image details and drawn control before any click',async()=>{
 let step=0;const pixels=new Uint8ClampedArray(100*100*4);
 const canvas={width:100,height:100,getBoundingClientRect:()=>({left:0,top:0,width:100,height:100}),getContext:()=>({getImageData:()=>({data:pixels})})};
 const editor={textContent:'Image Editor',querySelectorAll:s=>s==='canvas[part="remove-canvas"]'?[canvas]:[]};
 const wait=async check=>{for(step=0;step<6;step++){
  editor.textContent=step<2?'Image Editor':step<3?'GLOBAL-CFP-A1':'GLOBAL-CFP-A1 Uploaded image:';
  if(step===4)for(let y=30;y<42;y++)for(let x=40;x<52;x++)pixels[(y*100+x)*4+3]=255;
  const found=check();if(found)return found;
 }throw Error('Timeout');};
 const result=await prodigiResetControl(()=>step?editor:null,'GLOBAL-CFP-A1',wait,e=>e.textContent,()=>true);
 assert.equal(step,4);assert.equal(result.canvas,canvas);assert.deepEqual(result.point,{x:45.5,y:35.5});
});

test('Reset locates only the isolated rendered trash control, at its actual scale',()=>{
 const width=100,height=100,data=new Uint8ClampedArray(width*height*4);
 for(let y=40;y<52;y++)for(let x=12;x<24;x++)data[(y*width+x)*4+3]=255;
 const canvas={width,height,getBoundingClientRect:()=>({left:100,top:50,width:200,height:300}),getContext:()=>({getImageData:()=>({data})})};
 assert.deepEqual(prodigiRemovePoint(canvas),{x:135,y:186.5});
 data.fill(0);assert.throws(()=>prodigiRemovePoint(canvas),/cannot be identified/);
 data.fill(255);assert.throws(()=>prodigiRemovePoint(canvas),/cannot be identified/);
 assert.throws(()=>prodigiRemovePoint({...canvas,width:10000,height:10000}),/unavailable/);
 assert.throws(()=>prodigiRemovePoint({...canvas,getContext:()=>({getImageData(){throw Error('Tainted')}})}),/Tainted/);
});

test('remembered URL mode switches to file upload once and waits for its control',async()=>{
  const events=[],input={type:'file'};let mode='url',renders=0;
  const wait=async check=>{for(let n=0;n<4;n++){const result=check();if(result)return result;}throw Error('Not ready');};
  const get=()=>mode==='file'&&++renders>=2?input:null;
  const result=await prodigiFilePicker(get,async()=>events.push('options'),
    ()=>({click(){events.push('file mode');mode='file';}}),wait);
  assert.equal(result,input);assert.deepEqual(events,['options','file mode']);
  assert.equal(await prodigiFilePicker(()=>input,()=>assert.fail('Already in file mode'),()=>null,wait),input);
});

test('placement controls include nested open shadow components within this editor only',()=>{
  const fit={id:'fit'},save={id:'save'},other={id:'other-editor'};
  const root=(buttons,hosts=[])=>({querySelectorAll:s=>s==='button'?buttons:hosts});
  const nested={shadowRoot:root([fit])};
  const editor=root([save],[{shadowRoot:root([],[nested])}]);
  assert.deepEqual(prodigiControls(editor,'button'),[save,fit]);
  assert(!prodigiControls(editor,'button').includes(other));
});
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
  },crypto:webcrypto,Uint8Array,AbortSignal,URL,Date,setTimeout,clearTimeout,btoa:s=>Buffer.from(s,'binary').toString('base64'),
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

test('artwork replacement requires an exact live full-Reset handoff',()=>{
 const {context}=setup();context.plan={...plan,environment:'live',order_url:'https://dashboard.prodigi.com/orders/99/detail',
  key:'prodigi_prepare:1',token:'a'.repeat(43),exact_item:true,replace_artwork:true};
 assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),true);
 for(const change of [{exact_item:false},{item_id:''},{token:'invalid'},{key:'arbitrary'},{replace_artwork:'true'},
  {environment:'sandbox',order_url:plan.order_url}]){
  context.plan={...plan,environment:'live',order_url:'https://dashboard.prodigi.com/orders/99/detail',key:'prodigi_prepare:1',token:'a'.repeat(43),exact_item:true,replace_artwork:true,...change};
  assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),false);
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

test('certificate handoffs accept only scoped PDFs and reject crossed artwork plans',()=>{
  const {context}=setup();const certificate={...plan,kind:'certificate',
    artwork_url:plan.artwork_url.replace('prodigi-artwork','prodigi-document'),
    filename:'SC-1-certificate-'+'a'.repeat(16)+'.pdf'};
  context.plan=certificate;assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),true);
  for(const change of [{artwork_url:plan.artwork_url},{filename:plan.filename},{kind:'other'}]) {
    context.plan={...certificate,...change};assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),false);
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

test('sleeping owned page is woken once before fresh QA, retaining the new-page fence',async()=>{
 const {context,storage}=setup();const events=[];let awake=false,page='old';
 storage.ordersWorkerTabs={[plan.order_url]:9};
 context.setTimeout=(fn,ms)=>setTimeout(fn,ms===1500?5:ms);
 context.chrome.tabs.get=async id=>({id,url:plan.order_url});
 context.chrome.tabs.update=async(id,options)=>{assert.equal(id,9);assert.deepEqual(JSON.parse(JSON.stringify(options)),{active:true,autoDiscardable:false});events.push('wake');awake=true;};
 context.chrome.tabs.reload=async()=>{assert(awake);events.push('reload');page='new';};
 context.chrome.tabs.sendMessage=async()=>awake?{ready:true,page_instance:page}:await new Promise(()=>{});
 context.tab={id:9,url:plan.order_url,ordersReused:true};context.orderUrl=plan.order_url;
 assert.equal(await vm.runInContext('prodigiWaitForPage(tab,true,3,orderUrl)',context),true);
 assert.deepEqual(events,['wake','reload']);
});

test('sleep recovery never activates a user-navigated tab',async()=>{
 const {context,storage}=setup();storage.ordersWorkerTabs={[plan.order_url]:9};
 context.setTimeout=(fn,ms)=>setTimeout(fn,ms===1500?5:ms);
 context.chrome.tabs.get=async id=>({id,url:'https://dashboard.prodigi.com/orders/other/detail'});
 context.chrome.tabs.update=()=>assert.fail('User tab must not be activated');
 context.chrome.tabs.sendMessage=()=>new Promise(()=>{});
 context.tab={id:9};context.orderUrl=plan.order_url;
 await assert.rejects(vm.runInContext('prodigiWaitForPage(tab,false,1,orderUrl)',context),/changed before wake/);
 context.tab.ordersReused=true;context.chrome.tabs.reload=()=>assert.fail('User navigation must not be reloaded');
 await assert.rejects(vm.runInContext('prodigiWaitForPage(tab,true,1,orderUrl)',context),/changed before wake/);
});

test('ready probe releases its deadline on immediate response',async()=>{
 const {context}=setup();let cleared=0;context.clearTimeout=id=>{cleared++;clearTimeout(id);};
 assert.equal((await vm.runInContext('prodigiReadyProbe(9)',context)).ready,true);assert.equal(cleared,1);
});

test('upload and QA reuse only the worker-owned exact order tab',async()=>{
 const {context,tabs,storage}=setup();context.plan=plan;
 context.chrome.tabs.get=async id=>({id,url:plan.order_url});
 await vm.runInContext('prodigiWorkerTab(plan)',context);
 await vm.runInContext('prodigiWorkerTab(plan)',context);
 assert.equal(tabs.length,1);
 context.chrome.tabs.get=async id=>({id,url:'https://dashboard.prodigi.com/orders/different/detail'});
 await vm.runInContext('prodigiWorkerTab(plan)',context);
 assert.equal(tabs.length,2); // User navigation is preserved; no tabs.update call.
 context.chrome.tabs.get=async()=>{throw Error('Closed tab')};
 await vm.runInContext('prodigiWorkerTab(plan)',context);
 assert.equal(tabs.length,3);
});

test('blank product auto-opens an editor; fresh empty handoff reloads once then uploads and runs QA on the same tab',async()=>{
 const {context,tabs,storage}=setup();const events=[];let editor=false,page='old',oldReady=true,reloads=0;
 const live={...plan,environment:'live',order_url:'https://dashboard.prodigi.com/orders/99/detail',
   key:'prodigi_prepare:1',token:'a'.repeat(43),exact_item:true};
 context.chrome.tabs.get=async id=>({id,url:live.order_url});
 context.chrome.tabs.reload=async()=>{events.push('reload');editor=false;page='new-'+(++reloads);};
 context.chrome.tabs.sendMessage=async(id,m)=>{
   if(m.type==='prodigi:ready'){
     // A reload callback can resolve before the old content script disappears.
     if(page==='new-1'&&oldReady){oldReady=false;events.push('old-ready');return{ready:true,page_instance:'old'};}
     return{ready:true,page_instance:page,busy:editor};
   }
   if(m.type==='prodigi:product'){events.push('variant');editor=true;return{stage:'product-readback'};}
   if(m.type==='prodigi:upload'){assert(!editor);assert(!oldReady);events.push('upload');editor=true;return{saved:true,stage:'save'};}
   if(m.type==='prodigi:qa'){assert(!editor);events.push('qa');return{evidence:{}};}
   assert.fail('Unexpected message');
 };
 context.product={...live,kind:'product',key:'product:prodigi_prepare:1',sku:'GLOBAL-CFP-A2',colour:'Natural'};
 await vm.runInContext('prodigiBrowserRun(product)',context);
 context.upload={...live,selected_empty_product:true};
 await vm.runInContext('prodigiBrowserRun(upload)',context);
 context.qa={...live,kind:'qa',fresh_saved_order:true,sku:'GLOBAL-CFP-A2',colour:'Natural',shipping_intent:'standard',branding_set:'SC EDITION BRANDING'};
 await vm.runInContext('prodigiBrowserRun(qa)',context);
 assert.deepEqual(events,['variant','reload','old-ready','upload','reload','qa']);
 assert.equal(tabs.length,1);assert(!storage.ordersBrowserPending);
});

test('an ordinary saved artwork handoff never reloads an unexpected editor',async()=>{
 const {context}=setup();context.plan=plan;
 context.chrome.tabs.get=async id=>({id,url:plan.order_url});
 await vm.runInContext('prodigiWorkerTab(plan)',context);
 context.chrome.tabs.reload=()=>assert.fail('No empty product authority');
 await vm.runInContext('prodigiBrowserRun(plan)',context);
});

test('fresh saved-order QA removes only image-library filters on its owned exact tab',async()=>{
 const {context,storage,calls}=setup();let page='old',navigations=0;
 const url='https://dashboard.prodigi.com/orders/99/detail';
 storage.ordersWorkerTabs={[url]:9};
 context.chrome.tabs.get=async id=>({id,url:url+'?imageLibraryType=Uploads&imageLibraryFileType=Image'});
 context.chrome.tabs.reload=()=>assert.fail('Reload would retain stale library filters');
 context.chrome.tabs.update=async(id,options)=>{assert.equal(id,9);assert.deepEqual(JSON.parse(JSON.stringify(options)),{url});navigations++;page='new';};
 context.chrome.tabs.sendMessage=async(id,message)=>{
   if(message.type==='prodigi:ready')return {ready:true,page_instance:page};
   assert.equal(message.type,'prodigi:qa');assert.equal(page,'new');return{evidence:{}};
 };
 context.plan={kind:'qa',fresh_saved_order:true,environment:'live',order_id:'99',item_id:'88',exact_item:true,
   order_url:url,key:'prodigi_prepare:1',token:'b'.repeat(43),reference:'fixture',sku:'GLOBAL-CFP-A2',colour:'Black',shipping_intent:'standard',branding_set:'SC EDITION BRANDING'};
 await vm.runInContext('prodigiBrowserRun(plan)',context);
 assert.equal(navigations,1);assert.equal(calls.length,1);assert(calls[0].url.endsWith('/qa/finish'));
});

test('empty product editor authority rejects reset, sandbox and unscoped plans',()=>{
 const {context}=setup();const live={...plan,environment:'live',order_url:'https://dashboard.prodigi.com/orders/99/detail',
   key:'prodigi_prepare:1',token:'a'.repeat(43),exact_item:true,selected_empty_product:true};
 context.plan=live;assert(vm.runInContext('prodigiPlanValid(plan)',context));
 for(const change of [{exact_item:false},{replace_artwork:true},{kind:'certificate'},{selected_empty_product:'true'},
   {environment:'sandbox'},{key:'other'},{item_id:''},{token:'invalid'}]){
   context.plan={...live,...change};assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),false);
 }
});

test('read-only transport retries back off, while a Save permit is never retried',async()=>{
 const {context,storage}=setup();let calls=0;const delays=[];
 context.setTimeout=(fn,ms)=>{delays.push(ms);queueMicrotask(fn)};
 context.fetch=async()=>({ok:++calls===3,status:503});
 const result=await vm.runInContext("prodigiReadFetch('https://sports-cave-image-factory.onrender.com/readback',{})",context);
 assert(result.ok);assert.equal(calls,3);assert.deepEqual(delays,[1000,2000]);assert.equal(storage.ordersRetry.attempt,2);
 calls=0;context.plan=plan;context.fetch=async()=>{calls++;return{ok:false,status:503}};
 await assert.rejects(vm.runInContext("prodigiReceipt(plan,'permit')",context),/could not be verified/);assert.equal(calls,1);
});

test('merge Add plans accept only scoped live product-selection handoffs',()=>{
 const {context}=setup();const base={kind:'merge-add',environment:'live',order_id:'98',
   order_url:'https://dashboard.prodigi.com/orders/98/detail',key:'merge:prodigi_merge:'+'a'.repeat(32),
   token:'b'.repeat(43),sha256:'c'.repeat(64),reference:'fixture',sku:'GLOBAL-CFP-A2',colour:'Natural'};
 context.plan=base;assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),true);
 for(const change of [{key:'merge:arbitrary'},{environment:'sandbox'},{colour:'Oak'},
   {sku:'GLOBAL-CFP-A2-BACKLOADER'},{order_url:'https://dashboard.prodigi.com/orders/other/detail'}]){
   context.plan={...base,...change};assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),false);
 }
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


test('dashboard QA opens only the pinned live order and never downloads artwork',async()=>{
  const {context,calls,tabs}=setup();
  context.plan={kind:'qa',environment:'live',order_id:'99',order_url:'https://dashboard.prodigi.com/orders/99/detail',key:'prodigi_prepare:1',token:'b'.repeat(43),reference:'fixture',sku:'GLOBAL-CFP-A2',colour:'black',shipping_intent:'standard',branding_set:'SC EDITION BRANDING'};
  assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),true);
  await vm.runInContext('prodigiBrowserRun(plan)',context);
  assert.equal(tabs.length,1);assert.equal(tabs[0].active,false);
  assert.equal(calls.length,1);assert(calls[0].url.endsWith('/qa/finish'));
  context.plan.order_url='https://dashboard.prodigi.com/orders/other/detail';
  assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),false);
});
const {prodigiProductCard}=require('../windows-upload-companion/prodigi-page.js');
test('catalogue selection uses exact SKU and canonical colour, excluding backloader',()=>{
  const option={textContent:'Natural',value:'natural',disabled:false};
  const colour={options:[option],value:'black'};
  const target={getAttribute:()=> 'select-product-with-data-button-GLOBAL-CFP-A2',closest:()=>({querySelectorAll:()=>[colour]})};
  const backloader={getAttribute:()=> 'select-product-with-data-button-GLOBAL-CFP-A2-BACKLOADER'};
  const result=prodigiProductCard({querySelectorAll:()=>[backloader,target]},'GLOBAL-CFP-A2','Natural');
  assert.equal(result.select,target);assert.equal(result.value,'natural');
  assert.throws(()=>prodigiProductCard({querySelectorAll:()=>[target]},'GLOBAL-CFP-A2','White'));
  assert.throws(()=>prodigiProductCard({querySelectorAll:()=>[target,target]},'GLOBAL-CFP-A2','Natural'));
  assert.throws(()=>prodigiProductCard({querySelectorAll:()=>[backloader]},'GLOBAL-CFP-A2','Natural'));
});

test('batch QA plans require unique exact canonical items including the primary item',()=>{
 const {context}=setup();const base={kind:'qa',environment:'live',order_id:'99',item_id:'88',exact_item:true,
  order_url:'https://dashboard.prodigi.com/orders/99/detail',key:'prodigi_prepare:1',token:'a'.repeat(43),reference:'fixture',
  sku:'GLOBAL-CFP-A2',colour:'Natural',shipping_intent:'standard',branding_set:'SC EDITION BRANDING',
  items:[{item_id:'88',sku:'GLOBAL-CFP-A2',colour:'Natural'},{item_id:'89',sku:'GLOBAL-FAP-A4',colour:''}]};
 context.plan=base;assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),true);
 for(const change of [{items:[]},{exact_item:false},{items:[base.items[0],base.items[0]]},
  {item_id:'other'},{items:[base.items[0],{...base.items[1],sku:'GLOBAL-CFP-A2-BACKLOADER'}]},
  {items:[base.items[0],{...base.items[1],colour:'Black'}]}]){
  context.plan={...base,...change};assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),false);
 }
});
test('unframed catalogue selection has no colour option',()=>{
 const target={getAttribute:()=> 'select-product-with-data-button-GLOBAL-FAP-A4',closest:()=>({querySelectorAll:()=>[]})};
 assert.equal(prodigiProductCard({querySelectorAll:()=>[target]},'GLOBAL-FAP-A4','').select,target);
});
test('product repair opens only the pinned draft, without downloading artwork or submitting',async()=>{
 const {context,calls,tabs}=setup();
 context.plan={kind:'product',environment:'live',order_id:'99',item_id:'88',order_url:'https://dashboard.prodigi.com/orders/99/detail',key:'product:prodigi_prepare:1',token:'b'.repeat(43),sha256:'a'.repeat(64),reference:'fixture',sku:'GLOBAL-CFP-A2',colour:'Natural'};
 assert.equal(vm.runInContext('prodigiPlanValid(plan)',context),true);
 await vm.runInContext('prodigiBrowserRun(plan)',context);
 assert.equal(calls.length,1);assert(calls[0].url.endsWith('/browser/finish'));
 assert.equal(tabs.length,1);assert.equal(tabs[0].active,false);
 for(const change of [{sku:'GLOBAL-CFP-A2-BACKLOADER'},{colour:'Oak'},{environment:'sandbox'},{key:'prodigi_prepare:1'}]){
  context.changed={...context.plan,...change};assert.equal(vm.runInContext('prodigiPlanValid(changed)',context),false);
 }
});
for(const withCatalogueTab of [true,false])test('blank-product page flow with catalogue tab '+withCatalogueTab+' selects only after permit',async()=>{
 const listeners=[],events=[];let dialogOpen=false,selected=false,inputValue='';
 const node=(value='')=>({innerText:value,textContent:value,isConnected:true,getClientRects:()=>[{}],querySelectorAll:()=>[],getAttribute:()=>null});
 const control=(label,click)=>({...node(label),disabled:false,click});
 const code=node('GLOBAL-CFP-A2'),frame=node('Natural');
 const choose=control('Choose product',()=>{events.push('choose');dialogOpen=true;});choose.getAttribute=k=>k==='data-test'?'choose-product-button-88':null;choose.closest=()=>row;
 const row={...node(),querySelector:()=>selected?{}:null,querySelectorAll:s=>s==='button'?(selected?[]:[choose]):s==='strong'?(selected?[frame]:[]):selected?[code,frame]:[]};
 const colour={options:[{textContent:'Black',value:'black'},{textContent:'Natural',value:'natural'}],value:'black',dispatchEvent:()=>events.push('colour')};
 const select=control('Select',()=>{events.push('select');assert.equal(colour.value,'natural');selected=true;dialogOpen=false;});
 const card={querySelectorAll:()=>[colour]};select.closest=()=>card;select.getAttribute=k=>k==='data-test'?'select-product-with-data-button-GLOBAL-CFP-A2':null;
 const catalogue=control('Catalogue',()=>{});catalogue.getAttribute=k=>k==='aria-selected'?'true':null;
 class Input {dispatchEvent(){events.push('search:'+inputValue);}}
 Object.defineProperty(Input.prototype,'value',{get(){return inputValue;},set(v){inputValue=v;}});
 const input=new Input();
 const picker={...node(),querySelector:s=>s==='input[type="search"]'?input:null,querySelectorAll:s=>s==='h1,h2'?[node('Select product')]:s==='button'?(withCatalogueTab?[catalogue,select]:[select]):s==='button[data-test]'?[select]:[]};
 const document={readyState:'complete',querySelector:s=>s==='main'?node('fixture'):null,querySelectorAll:s=>s==='button[data-test]'?[choose]:s==='h1'?[node('99')]:s==='strong'?[]:s==='[role="dialog"]'?(dialogOpen?[picker]:[]):s==='table tbody tr'?[row]:[]};
 const chrome={runtime:{id:'same',onMessage:{addListener:f=>listeners.push(f)},sendMessage:async m=>{events.push('permit');assert(selected===false);assert.equal(m.type,'prodigi:permit');return{permitted:true};}}};
 const ctx=vm.createContext({document,chrome,location:{href:'https://dashboard.prodigi.com/orders/99/detail'},URL,Date,setTimeout,HTMLInputElement:Input,Event:class{constructor(type){this.type=type;}}});
 vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../windows-upload-companion/prodigi-page.js'),'utf8'),ctx);
 const result=await new Promise(resolve=>listeners[0]({type:'prodigi:product',plan:{environment:'live',order_url:'https://dashboard.prodigi.com/orders/99/detail',order_id:'99',item_id:'88',reference:'fixture',sku:'GLOBAL-CFP-A2',colour:'Natural',sha256:'a'.repeat(64)}},{id:'same'},resolve));
 assert.equal(result.stage,'product-readback');assert.deepEqual(events,['choose','search:GLOBAL-CFP-A2','colour','permit','select']);
});
const {prodigiPinnedRow}=require('../windows-upload-companion/prodigi-page.js');
for(const permitted of [true,false])test('paused order Add another item selects its exact variant only after permit '+permitted,async()=>{
 const listeners=[],events=[];let open=false;
 const node=(value='')=>({innerText:value,textContent:value,isConnected:true,getClientRects:()=>[{}],querySelectorAll:()=>[],getAttribute:()=>null});
 const button=(label,click)=>({...node(label),disabled:false,click});
 const add=button('Add another item',()=>{events.push('open-picker');open=true;});
 const option={textContent:'Natural',value:'natural',disabled:false};
 const colour={options:[option],value:'black',dispatchEvent(){events.push('colour')}};
 const select=button('Select',()=>{events.push('select');open=false;});
 select.getAttribute=()=> 'select-product-with-data-button-GLOBAL-CFP-A2';select.closest=()=>({querySelectorAll:()=>[colour]});
 class Input{set value(v){this.v=v}get value(){return this.v}dispatchEvent(){events.push('search:'+this.v)}}
 const search=new Input(),heading=node('Select product');
 const picker={...node('Select product'),querySelector:s=>s==='input[type="search"]'?search:null,
  querySelectorAll:s=>s==='h1,h2'?[heading]:s==='button'||s==='button[data-test]'?[select]:[]};
 const document={querySelector:s=>s==='main'?node('original-reference'):null,
  querySelectorAll:s=>s==='button'?[add]:s==='h1'?[node('98')]:s==='[role="dialog"]'?(open?[picker]:[]):[]};
 const chrome={runtime:{id:'same',onMessage:{addListener:f=>listeners.push(f)},sendMessage:async()=>{events.push('permit');return{permitted,order_id:'98',operation:'add-item'}}}};
 const ctx=vm.createContext({document,chrome,location:{href:'https://dashboard.prodigi.com/orders/98/detail'},URL,Date,setTimeout,HTMLInputElement:Input,Event:class{}});
 vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../windows-upload-companion/prodigi-page.js'),'utf8'),ctx);
 const result=await new Promise(resolve=>listeners[0]({type:'prodigi:merge-add',plan:{environment:'live',order_url:'https://dashboard.prodigi.com/orders/98/detail',order_id:'98',reference:'original-reference',sku:'GLOBAL-CFP-A2',colour:'Natural',sha256:'a'.repeat(64)}},{id:'same'},resolve));
 assert.equal(result.stage,permitted?'product-readback':'product-select');
 assert.deepEqual(events,permitted?['open-picker','search:GLOBAL-CFP-A2','colour','permit','select']:['open-picker','search:GLOBAL-CFP-A2','colour','permit']);
});
test('identical SKU and frame rows are distinguished by immutable item ID',()=>{
 const row=id=>({querySelector:s=>s==='[data-test="line-item-preview-'+id+'"]'?{}:null,querySelectorAll:s=>s==='strong'?[{textContent:'Black'}]:[{textContent:'GLOBAL-CFP-A2'}]});
 const one=row('88'),two=row('89'),plan={sku:'GLOBAL-CFP-A2',colour:'black',item_id:'89',exact_item:true};
 assert.equal(prodigiPinnedRow([one,two],plan),two);
 assert.equal(prodigiPinnedRow([one],plan),null);
 assert.throws(()=>prodigiPinnedRow([one,two],{...plan,exact_item:false}));
});

const {prodigiIndefiniteHold}=require('../windows-upload-companion/prodigi-page.js');
test('an old indefinite-hold history entry never overrides a live finite countdown',()=>{
 const scope={querySelectorAll:s=>s==='h1,h2,h3'?[{label:'23h until production'}]:[]};
 const text=e=>e===scope?'Order paused indefinitely (history)':e.label;
 assert.equal(prodigiIndefiniteHold(scope,text,()=>true),false);
 scope.querySelectorAll=()=>[];assert.equal(prodigiIndefiniteHold(scope,text,()=>true),true);
});
for(const alreadyHeld of [false,true])test('duplicate hold is source-scoped and never changes an existing indefinite hold '+alreadyHeld,async()=>{
 const listeners=[],events=[];let held=alreadyHeld;
 const node=value=>({innerText:value,textContent:value,isConnected:true,getClientRects:()=>[{}],querySelectorAll:()=>[],getAttribute:()=>null});
 const pause={...node('Pause indefinitely'),click(){events.push('hold-source');held=true;}};
 const main={get innerText(){return 'reference-source '+(held?'Paused indefinitely':'Paused')},get textContent(){return this.innerText},
  querySelectorAll:s=>s==='h1,h2,h3'?[node(held?'Paused indefinitely':'23h until production')]:s==='button'?(held?[]:[pause]):[]};
 const document={querySelector:s=>s==='main'?main:null,querySelectorAll:s=>s==='h1'?[node('99')]:s==='button'?(held?[]:[pause]):[]};
 const chrome={runtime:{id:'same',onMessage:{addListener:f=>listeners.push(f)},sendMessage:async()=>{events.push('permit-source');return{permitted:true,order_id:'99',operation:'hold-duplicate'}}}};
 const ctx=vm.createContext({document,chrome,location:{href:'https://dashboard.prodigi.com/orders/99/detail'},URL,Date,setTimeout});
 vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../windows-upload-companion/prodigi-page.js'),'utf8'),ctx);
 const result=await new Promise(resolve=>listeners[0]({type:'prodigi:merge-hold',plan:{environment:'live',order_url:'https://dashboard.prodigi.com/orders/99/detail',order_id:'99',reference:'reference-source',sha256:'a'.repeat(64)}},{id:'same'},resolve));
 assert.equal(result.stage,'merge-hold-confirmed');assert.deepEqual(events,alreadyHeld?['permit-source']:['permit-source','hold-source']);
});
