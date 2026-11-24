'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../windows-upload-companion/prodigi-page.js'),'utf8');
function setup({busyUntil=0,ignoreClicks=0,hasImage=true}={}){
 let clock=0,clicks=0,loaded=false,pins=0;
 const plan={filename:'SC-1-aaaaaaaaaaaaaaaa-bbbbbbbb.jpg',dimensions:[4200,5940]};
 const caption={textContent:plan.filename.replace('.jpg','')};
 const image={disabled:false,textContent:caption.textContent+' 4200x5940px jpg',querySelector:()=>caption,
  click(){clicks++;if(clock>=busyUntil&&clicks>ignoreClicks)loaded=true;}};
 const busy={disabled:true,textContent:'Uploading...'};
 const picker={querySelectorAll:s=>s==='button'?(clock<busyUntil?[busy]:[]):hasImage?[image]:[]};
 const ctx=vm.createContext({module:{exports:{}},URL,Date:{now:()=>clock}});vm.runInContext(source,ctx);
 const wait=async(check,timeout=600000)=>{for(clock=0;clock<=timeout;clock+=1000){const value=check();if(value)return value;}
  throw Error('The expected Prodigi control did not finish loading.');};
 const run=()=>ctx.module.exports.prodigiUploadedEditor(plan,()=>({textContent:'Uploaded image: 4200x5940px'}),
  ()=>loaded?null:picker,wait,()=>{pins++;},e=>e?.textContent||'',()=>true);
 return{ctx,run,plan,image,get clock(){return clock},get clicks(){return clicks},get pins(){return pins}};
}

test('a completed tile waits for the supplier upload control to settle before selection',async()=>{
 const h=setup({busyUntil:8000});assert(await h.run());assert.equal(h.clicks,1);assert.equal(h.clock,9000);
});
test('an ignored first library selection is retried on the same image without upload or Save',async()=>{
 const h=setup({ignoreClicks:1});assert(await h.run());assert.equal(h.clicks,2);assert(h.clock>=5000&&h.clock<20000);
});
test('a stuck busy flag after the completed tile has a precise bounded recovery cause',async()=>{
 const h=setup({busyUntil:Infinity});await assert.rejects(h.run(),/library stayed busy after the uploaded image became available/);
 assert.equal(h.clicks,0);assert(h.clock<=60000);
});
test('persistent ignored selection is bounded and distinguishable from upload failure',async()=>{
 const h=setup({ignoreClicks:Infinity});await assert.rejects(h.run(),/image selection did not finish after the verified library image became ready/);
 assert.equal(h.clicks,3);assert(h.clock<=45000);
});
test('an upload with no completed tile reports the upload timeout',async()=>{
 const h=setup({hasImage:false,busyUntil:Infinity});await assert.rejects(h.run(),/image upload did not finish within the allowed time/);assert.equal(h.clicks,0);
});
test('an absent tile without a busy upload reports missing library evidence',async()=>{
 const h=setup({hasImage:false});await assert.rejects(h.run(),/uploaded image did not become available in the Prodigi picker/);assert.equal(h.clicks,0);
});
test('mismatched image dimensions remain fatal before any selection',async()=>{
 const h=setup();h.image.textContent='4200x5941px';await assert.rejects(h.run(),/dimensions differ/);assert.equal(h.clicks,0);
});
test('changed order identity is checked before each selection retry',async()=>{
 const h=setup({ignoreClicks:Infinity});let calls=0;
 await assert.rejects(h.ctx.module.exports.prodigiUploadedEditor(h.plan,()=>null,()=>({querySelectorAll:s=>s==='button'?[]:[h.image]}),
  async check=>{for(let n=0;n<10;n++)check();},()=>{if(++calls>2)throw Error('Order changed');},e=>e?.textContent||'',()=>true),/Order changed/);
 assert.equal(h.clicks,1);
});
