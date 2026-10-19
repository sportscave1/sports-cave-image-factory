const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),{webcrypto}=require('node:crypto');
const settle=()=>new Promise(r=>setImmediate(r));
async function fixture(modern=false){
 const elements={},events={},timers=new Map(),calls=[],writes=[],observers=[];let clock=0,seq=0,denied=false,delay=null;
 let row={id:'first',name:'Selected.psd',mode:'DRAFT',state:'Ready',basic_validated:true,saved_source_version:'source-1'};
 const el=id=>elements[id]??={value:id==='mode'?'DRAFT':'',hidden:true,disabled:false,children:[],html:id==='copy'?'Copy Complete Upload Prompt':'',
  get textContent(){return this.html},set textContent(x){this.html=x},get innerHTML(){return this.html},set innerHTML(x){this.html=x},
  setAttribute(){},removeAttribute(){},addEventListener(){},replaceChildren(...x){this.children=x},append(x){this.children.push(x)},
  getBoundingClientRect(){return {height:80}},focus(){}};
 const parent={postMessage(){},document:{}},frame={isConnected:true};
 const ctx={console,AbortController,Blob,URL,crypto:webcrypto,Date,location:{origin:'http://fixture'},parent,
  document:{getElementById:el,body:el('body'),hidden:false,addEventListener:(n,f)=>events[n]=f},
  setTimeout:(fn,ms)=>{let id=++seq;timers.set(id,{fn,at:clock+ms});return id},clearTimeout:id=>timers.delete(id),
  ResizeObserver:class{observe(){}},MutationObserver:class{constructor(fn){observers.push(fn)}observe(){}disconnect(){}},
  navigator:{clipboard:{writeText:async text=>{if(denied)throw Error('Clipboard denied');writes.push(text)}}},
  fetch:async(url,options={})=>{
   const body=options.body?JSON.parse(options.body):{};calls.push({url,body});
   if(url.endsWith('/prompt')){const text='Complete '+body.mode+' '+body.source_version;if(delay)await delay;return {ok:true,status:200,json:async()=>({prompt:text})};}
   if(url.endsWith('/mode'))row={...row,mode:body.mode};
   return {ok:true,status:200,json:async()=>({enabled:true,upload:row?{...row}:null})};
  },ProductUploadMapping:()=>({sync(){},reset(){},dispose(){}}),addEventListener:(n,f)=>events[n]=f};
 if(modern){ctx.ClipboardItem=class{constructor(data){this.data=data}};ctx.navigator.clipboard.write=async items=>{if(denied)throw Error('Clipboard denied');writes.push(await (await items[0].data['text/plain']).text());};}
 ctx.window=ctx;ctx.frameElement=frame;
 vm.runInNewContext(fs.readFileSync('components/product_uploads/app.js','utf8'),ctx);await settle();
 return {el,events,timers,calls,writes,frame,observers,
  tick(ms){clock+=ms;for(const [id,t] of [...timers])if(t.at<=clock){timers.delete(id);t.fn();}},
  deny(v){denied=v},delay(){let resolve;delay=new Promise(r=>resolve=r);return ()=>{resolve();delay=null}},
  async source(version,id='first'){row={...row,id,saved_source_version:version,preview_url:'/preview-must-not-load-in-handoff'};events.message({source:parent,data:{type:'streamlit:render',args:{section:'handoff',id,mode:row.mode,source_version:version||''}}});await settle();},
  async mode(mode){el('mode').value=mode;await el('mode').onchange();}
 };
}
(async()=>{
 for(const modern of [false,true]){
  const f=await fixture(modern);assert(!f.el('copy').disabled);
  for(const mode of ['DRAFT','LIVE','UPDATE']){
   await f.mode(mode);await f.el('copy').onclick();assert.equal(f.el('copy').textContent,'Copied');
   assert.equal(f.writes.at(-1),'Complete '+mode+' source-1');
   f.tick(1999);assert.equal(f.el('copy').textContent,'Copied');f.tick(1);assert.equal(f.el('copy').textContent,'Copy Complete Upload Prompt');
  }
  await f.el('copy').onclick();f.tick(1000);await f.el('copy').onclick();f.tick(1000);assert.equal(f.el('copy').textContent,'Copied');f.tick(1000);assert.equal(f.el('copy').textContent,'Copy Complete Upload Prompt');
  f.deny(true);await f.el('copy').onclick();assert.match(f.el('error').textContent,/Clipboard denied/);assert.equal(f.el('copy').textContent,'Copy Complete Upload Prompt');assert.equal(f.timers.size,0);
  f.deny(false);await f.source(undefined);assert(f.el('copy').disabled);assert(f.el('prompt').hidden);assert(f.el('return').hidden);let count=f.calls.length;await f.el('copy').onclick();assert.equal(f.calls.length,count);
  await f.source('source-2');const resolve=f.delay(),before=f.writes.length,old=f.el('copy').onclick();await settle();await f.source('source-3','new-product');resolve();await old;assert.equal(f.writes.length,before);
  await f.el('copy').onclick();assert.equal(f.writes.at(-1),'Complete UPDATE source-3');
  f.events.pagehide();assert.equal(f.timers.size,0);
  assert(f.calls.every(x=>/\/(state(?:\?|$)|prompt$|mode$|copied$)/.test(x.url)));
 }
 const f=await fixture();await f.el('copy').onclick();f.frame.isConnected=false;f.observers.forEach(fn=>fn());assert.equal(f.timers.size,0);
 const markup=fs.readFileSync('components/product_uploads/index.html','utf8');
 assert(!/saved-grid|saved-files|saved-card|Copy unavailable|Download WEBP|product-upload-package.js|textarea/.test(markup.replace(/dialog textarea\{[^}]+\}/,'')));
 assert(markup.includes('id="preview"')&&markup.includes('id="choose"')&&markup.includes('id="map"'));
 assert.equal((markup.match(/id="copy"/g)||[]).length,1);
 console.log('PASS: complete prompt clipboard in both APIs; all modes; save gate; errors; 2000ms feedback; retries; stale responses; new product; timer cleanup; no gallery or image/helper requests.');
})().catch(e=>{console.error(e);process.exitCode=1});
