'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const {prodigiLibraryImage,prodigiUploadedEditor}=require('../windows-upload-companion/prodigi-page.js');
const plan={filename:'SC-1-aaaaaaaaaaaaaaaa-bbbbbbbb.jpg',dimensions:[4200,5940],library_asset_id:'asset-id'};
const text=e=>e?.textContent||'',visible=()=>true;
function tile(changes={}){return{disabled:false,textContent:plan.filename.replace('.jpg','')+' 4200x5940px jpg',
 querySelector:()=>({textContent:plan.filename.replace('.jpg','')}),querySelectorAll:()=>[{getAttribute:()=> 'https://live-services.pwinty.com/image-library/image/asset-id/thumbnail/small?opaque=value'}],...changes};}
test('completed upload in picker is selected once, without sending another file',async()=>{
 let step=0,clicks=0,pins=0;const image=tile({click(){clicks++;}}),picker={querySelectorAll:()=>step>=2?[image]:[]};
 const editor={textContent:'Uploaded image: 4200x5940px'};
 const result=await prodigiUploadedEditor(plan,()=>editor,()=>step<5?picker:null,async check=>{
  for(step=0;step<8;step++){const found=check();if(found)return found;}throw Error('Never loaded');
 },()=>pins++,text,visible);
 assert.equal(result,editor);assert.equal(clicks,1);assert.equal(pins,6);
});
test('normal automatic selection continues without touching the library',async()=>{
 const editor={textContent:'Uploaded image: 4200x5940px'};
 assert.equal(await prodigiUploadedEditor(plan,()=>editor,()=>null,async check=>check(),()=>{},text,visible),editor);
});
for(const change of ['duplicate','dimensions','asset','disabled','unrelated'])test('picker rejects unsafe candidate: '+change,()=>{
 let image=tile();if(change==='dimensions')image.textContent='4200x5941px';
 if(change==='asset')image.querySelectorAll=()=>[{getAttribute:()=> 'https://live-services.pwinty.com/image-library/image/other/thumbnail/small'}];
 if(change==='disabled')image.disabled=true;
 if(change==='unrelated')image.querySelector=()=>({textContent:'some-other.jpg'});
 const scope={querySelectorAll:()=>change==='duplicate'?[image,image]:[image]};
 if(['disabled','unrelated'].includes(change))assert.equal(prodigiLibraryImage(scope,plan,text,visible),null);
 else assert.throws(()=>prodigiLibraryImage(scope,plan,text,visible));
});
test('changed order identity aborts before any library click',async()=>{
 await assert.rejects(prodigiUploadedEditor(plan,()=>null,()=>({querySelectorAll:()=>[tile({click(){assert.fail('Changed order');}})]}),
  async check=>check(),()=>{throw Error('Order changed');},text,visible),/Order changed/);
});
test('persistent library JWT error becomes a precise recoverable failure',async()=>{
 const source=fs.readFileSync(require.resolve('../windows-upload-companion/prodigi-page.js'),'utf8');
 let clock=0;const ctx=vm.createContext({Date:{now:()=>clock},module:{exports:{}},URL});vm.runInContext(source,ctx);
 await assert.rejects(ctx.module.exports.prodigiUploadedEditor(plan,()=>null,()=>({textContent:'Invalid JWT token Error code: 401',querySelectorAll:()=>[]}),
 async check=>{for(clock=0;clock<30000;clock+=1000)check();},()=>{},text,visible),/authentication expired/);
 assert.equal(clock,20000);
});
test('lost finish acknowledgement retains the exact Save completion and retries readback only',async()=>{
 const source=fs.readFileSync(require.resolve('../windows-upload-companion/prodigi-browser.js'),'utf8');
 const storage={staffQueueCredential:'paired'},sent=[],pending={...plan,kind:'qa',key:'prodigi_prepare:1',token:'a'.repeat(43),
   ordersCompletion:{stage:'qa',error:'',evidence:{quality:'Excellent',item_id:'88'}}};
 let online=false;
 const ctx=vm.createContext({chrome:{storage:{local:{get:async()=>storage,set:async v=>Object.assign(storage,v),remove:async k=>delete storage[k]}},runtime:{onMessage:{addListener(){}}}},
  fetch:async(url,options)=>{sent.push(JSON.parse(options.body));if(!online)throw Error('Offline');return{ok:true,json:async()=>({status:'Ready for manual payment'})};},
  AbortSignal,URL,Date,setTimeout:fn=>{queueMicrotask(fn)},clearTimeout(){},osOrigin:'https://sports-cave-image-factory.onrender.com'});
 vm.runInContext(source,ctx);ctx.plan=pending;storage.ordersBrowserPending=pending;
 await assert.rejects(vm.runInContext('prodigiResumeCompletion(plan)',ctx),/Offline/);
 assert.equal(storage.ordersBrowserPending,pending);online=true;
 assert.equal((await vm.runInContext('prodigiResumeCompletion(plan)',ctx)).status,'Ready for manual payment');
 assert.equal(storage.ordersBrowserPending,undefined);
 assert(sent.every(body=>JSON.stringify(body.evidence)===JSON.stringify(pending.ordersCompletion.evidence)));
 assert(sent.every(body=>body.key===pending.key&&body.token===pending.token));
});
for(const ignoredClicks of [0,1])test('full recovered page flow Saves once with no file transfer, ignored selections: '+ignoredClicks,async()=>{
 let listener,editorOpen=false,pickerOpen=false,loaded=false,permits=0,saves=0,selects=0,clock=0;
 const node=textContent=>({textContent,isConnected:true,getClientRects:()=>[{}],getAttribute:()=>null});
 const button=(name,click)=>({...node(name),disabled:false,click});
 const upload=button('Upload',()=>editorOpen=true),add=button('Add image',()=>pickerOpen=true),
  fit=button('fit',()=>{}),save=button('Save',()=>{saves++;editorOpen=false;});
 const caption=node(plan.filename.replace('.jpg',''));
 const image={...tile(),...node(caption.textContent+' 4200x5940px jpg'),querySelector:()=>caption,
  querySelectorAll:()=>[{getAttribute:()=> 'https://live-services.pwinty.com/image-library/image/asset-id/thumbnail/small'}],
  click(){selects++;if(selects<=ignoredClicks)return;loaded=true;pickerOpen=false;}};
 const editor={...node('GLOBAL-CFP-A2'),get textContent(){return 'GLOBAL-CFP-A2 '+(loaded?'Uploaded image: 4200x5940px':'');},
  querySelectorAll:s=>s==='h1,h2'?[node('Image Editor')]:s==='button'?[add,fit,save]:[]};
 const picker={...node('Select image'),querySelectorAll:s=>s==='h1,h2'?[node('Select image')]:s==='button[data-test^="image-library-tile-"]'?[image]:[]};
 const row={...node(''),querySelector:s=>s==='[data-test="line-item-preview-88"]'?{}:null,
  querySelectorAll:s=>s==='*'?[node('GLOBAL-CFP-A2')]:s==='button'?[upload]:[]};
 const document={querySelector:()=>node('fixture'),querySelectorAll:s=>s==='[role="dialog"]'?[...(editorOpen?[editor]:[]),...(pickerOpen?[picker]:[])]:s==='h1'?[node('99')]:s==='table tbody tr'?[row]:[]};
 const ctx=vm.createContext({document,URL,Date:{now:()=>clock},setTimeout:(fn,ms)=>{clock+=ms;queueMicrotask(fn);},location:{href:'https://dashboard.prodigi.com/orders/99/detail',pathname:'/orders/99/detail'},
  chrome:{runtime:{id:'paired',onMessage:{addListener:f=>listener=f},sendMessage:async m=>{assert.equal(m.type,'prodigi:permit');permits++;return{permitted:true};}}}});
 vm.runInContext(fs.readFileSync(require.resolve('../windows-upload-companion/prodigi-page.js'),'utf8'),ctx);
 const result=await new Promise(resolve=>listener({type:'prodigi:upload',plan:{...plan,sha256:'a'.repeat(64),environment:'live',order_url:ctx.location.href,
  order_id:'99',reference:'fixture',item_id:'88',exact_item:true,sku:'GLOBAL-CFP-A2',colour:''}},{id:'paired'},resolve));
 assert.equal(result.saved,true);assert.equal(selects,ignoredClicks+1);assert.equal(permits,1);assert.equal(saves,1);
});
test('worker preserves completed QA evidence when all finish responses are lost',async()=>{
 const storage={staffQueueCredential:'paired'},qaPlan={kind:'qa',environment:'live',order_id:'99',
  order_url:'https://dashboard.prodigi.com/orders/99/detail',key:'prodigi_prepare:1',token:'a'.repeat(43),
  reference:'fixture',sku:'GLOBAL-CFP-A2',colour:'Black',shipping_intent:'standard',branding_set:'SC EDITION BRANDING'};
 const ctx=vm.createContext({chrome:{storage:{local:{get:async()=>storage,set:async v=>Object.assign(storage,v),remove:async k=>delete storage[k]}},
  runtime:{onMessage:{addListener(){}}},tabs:{create:async()=>({id:9}),get:async id=>({id,url:qaPlan.order_url}),sendMessage:async(id,m)=>m.type==='prodigi:ready'?{ready:true}:{evidence:{quality:'Excellent'}}}},
  fetch:async()=>{throw Error('Offline');},AbortSignal,URL,Date,setTimeout,clearTimeout,osOrigin:'https://sports-cave-image-factory.onrender.com'});
 vm.runInContext(fs.readFileSync(require.resolve('../windows-upload-companion/prodigi-browser.js'),'utf8'),ctx);ctx.plan=qaPlan;
 await assert.rejects(vm.runInContext('prodigiBrowserRun(plan)',ctx),/Offline/);
 assert.deepEqual(JSON.parse(JSON.stringify(storage.ordersBrowserPending.ordersCompletion)),{stage:'product',error:'',evidence:{quality:'Excellent'}});
 assert.equal(storage.ordersBrowserPending.ordersCompletion.error,'');
});
