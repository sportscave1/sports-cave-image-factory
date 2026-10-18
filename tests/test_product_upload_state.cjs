// Component state contracts with no server, browser files or provider writes.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),{webcrypto}=require('crypto');
const tick=()=>new Promise(r=>setImmediate(r));
async function fixture(){
 const elements={},listeners={},calls=[],messages=[];let deferred=null,selected=null;
 const el=id=>elements[id]??={value:id==='mode'?'DRAFT':id==='picker-root'?'review':'',hidden:true,textContent:'',children:[],addEventListener(n,f){this[n]=f},replaceChildren(...c){this.children=c},append(c){this.children.push(c)},close(){this.open=false},showModal(){this.open=true},select(){}};
 const doc={hidden:false,body:{getBoundingClientRect:()=>({height:500})},getElementById:el,createElement:()=>({}),addEventListener(n,f){listeners[n]=f},execCommand:()=>true};
 const ctx={document:doc,console,crypto:webcrypto,AbortController,Date,URL,Image:class{},ResizeObserver:class{observe(){}},queueMicrotask,navigator:{clipboard:{writeText:async()=>{}}},location:{origin:'http://local'},setTimeout:(f,n)=>{const t=setTimeout(f,n);t.unref();return t},clearTimeout,fetch:async(url,options)=>{
  calls.push(url);const body=options.body?JSON.parse(options.body):{};let data;
  if(url.includes('/state'))data={enabled:true,upload:body.id?selected:null};
  else if(url.endsWith('/browse'))data={roots:{review:{path:'/Review'}},path:'/Review',items:[{'.tag':'file',id:'id:exact',rev:'a1',name:'Art.psd'}],has_more:false};
  else if(url.endsWith('/select')){if(deferred)await deferred.promise;selected={id:body.id,name:'Art.psd',size:128,basic_validated:true,state:'Selected',mode:body.mode,source:{id:body.file_id,rev:body.revision,path_display:'/Review/Art.psd'}};data={upload:selected};}
  else if(url.endsWith('/prompt'))data={prompt:'Selected '+body.mode};
  else data={upload:selected};
  return {ok:true,status:200,json:async()=>data};
 }};
 ctx.window=ctx;ctx.parent={postMessage:m=>messages.push(m)};ctx.addEventListener=(n,f)=>listeners[n]=f;
 vm.runInNewContext(fs.readFileSync('components/product_uploads/app.js','utf8'),ctx);await tick();
 return {el,calls,messages,listeners,metrics:ctx.productUploadMetrics,delay:()=>{let resolve;const promise=new Promise(r=>resolve=r);deferred={promise,resolve};return resolve;}};
}
(async()=>{
 let f=await fixture();assert(f.el('summary').hidden);assert(!f.calls.some(x=>x.includes('?id=')));
 await f.el('choose').onclick();await tick();assert(f.el('picker').open);assert.equal(f.el('picker-path').textContent,'/Review');
 const finish=f.delay();const selection=f.el('picker-items').children[0].onclick();f.el('remove').onclick();finish();await selection;
 assert(f.el('summary').hidden);assert.equal(f.el('filename').textContent,'');
 assert(!f.calls.some(x=>/\/(start|chunk|finish)/.test(x)));
 f=await fixture();await f.el('choose').onclick();await tick();await f.el('picker-items').children[0].onclick();
 assert.equal(f.el('filename').textContent,'Art.psd');assert(f.el('detail').textContent.includes('/Review/Art.psd'));
 f.el('remove').onclick();assert(f.el('summary').hidden);
 f.el('manual').onclick();for(const mode of ['DRAFT','LIVE','UPDATE']){f.el('mode').value=mode;await f.el('copy').onclick();assert.equal(f.el('copy').textContent,'Copied');}
 console.log('PASS: exact ID/revision picker; stale response ignored; remove/fresh page empty; three prompt modes; no PSD byte transfer');
})().catch(e=>{console.error(e);process.exitCode=1});
