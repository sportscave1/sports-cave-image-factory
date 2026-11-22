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
test('identical SKU and frame rows are distinguished by immutable item ID',()=>{
 const row=id=>({querySelector:s=>s==='[data-test="line-item-preview-'+id+'"]'?{}:null,querySelectorAll:s=>s==='strong'?[{textContent:'Black'}]:[{textContent:'GLOBAL-CFP-A2'}]});
 const one=row('88'),two=row('89'),plan={sku:'GLOBAL-CFP-A2',colour:'black',item_id:'89',exact_item:true};
 assert.equal(prodigiPinnedRow([one,two],plan),two);
 assert.equal(prodigiPinnedRow([one],plan),null);
 assert.throws(()=>prodigiPinnedRow([one,two],{...plan,exact_item:false}));
});
