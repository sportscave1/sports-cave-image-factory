// Component state contracts with no server, browser files or provider writes.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),{webcrypto}=require('crypto');
const tick=()=>new Promise(r=>setImmediate(r));
async function fixture(){
 const elements={},listeners={},calls=[],messages=[];let deferred=null,selected=null,browseDeferred=null,failPrepare=false,prepareDeferred=null;
 const el=id=>elements[id]??={value:id==='mode'?'DRAFT':id==='picker-root'?'review':'',hidden:true,textContent:'',children:[],setAttribute(n,v){this[n]=v},removeAttribute(n){delete this[n]},addEventListener(n,f){if(n==='close')this.onclose=f;else this[n]=f},replaceChildren(...c){this.children=c},append(c){this.children.push(c)},close(){this.open=false},showModal(){this.open=true},select(){},focus(){this.focused=true}};
 const doc={hidden:false,body:{getBoundingClientRect:()=>({height:500})},getElementById:el,createElement:()=>({}),addEventListener(n,f){listeners[n]=f},execCommand:()=>true};
 const ctx={document:doc,console,crypto:webcrypto,AbortController,Date,URL,Image:class{},ResizeObserver:class{observe(){}},queueMicrotask,navigator:{clipboard:{writeText:async()=>{}}},location:{origin:'http://local'},setTimeout:(f,n)=>{const t=setTimeout(f,n);t.unref();return t},clearTimeout,fetch:async(url,options)=>{
  calls.push(url);const body=options.body?JSON.parse(options.body):{};let data;
  if(url.includes('/state'))data={enabled:true,upload:body.id?selected:null};
  else if(url.endsWith('/browse')){if(browseDeferred)await browseDeferred.promise;data={roots:{review:{path:'/Review'}},path:'/Review',items:[{'.tag':'file',id:'id:exact',rev:'a1',name:'Art.psd'}],has_more:false};}
  else if(url.endsWith('/select')){if(deferred)await deferred.promise;selected={id:body.id,name:'Art.psd',size:128,basic_validated:true,state:'Selected',mode:body.mode,source:{id:body.file_id,rev:body.revision,path_display:'/Review/Art.psd'}};data={upload:selected};}
  else if(url.endsWith('/prepare')){const owned=selected;if(prepareDeferred){const pending=prepareDeferred;prepareDeferred=null;await pending.promise;}if(failPrepare){selected={...selected,state:'Error',reason:'Original PSD download interrupted.'};return {ok:false,status:503,json:async()=>({error:selected.reason,upload:selected})};}selected={...owned,state:'Ready',reason:''};data={upload:selected};}
  else if(url.endsWith('/prompt'))data={prompt:'Selected '+body.mode};
  else data={upload:selected};
  return {ok:true,status:200,json:async()=>data};
 }};
 ctx.window=ctx;ctx.parent={postMessage:m=>messages.push(m)};ctx.addEventListener=(n,f)=>listeners[n]=f;
 vm.runInNewContext(fs.readFileSync('components/product_uploads/app.js','utf8'),ctx);await tick();
 return {el,calls,messages,listeners,metrics:ctx.productUploadMetrics,delayPreparation:()=>{let resolve;const promise=new Promise(r=>resolve=r);prepareDeferred={promise,resolve};return resolve;},failPreparation:value=>{failPrepare=value},delayBrowse:()=>{let resolve;const promise=new Promise(r=>resolve=r);browseDeferred={promise,resolve};return resolve;},delay:()=>{let resolve;const promise=new Promise(r=>resolve=r);deferred={promise,resolve};return resolve;}};
}
(async()=>{
 let f=await fixture();assert(f.el('summary').hidden);assert(!f.calls.some(x=>x.includes('?id=')));
 await f.el('choose').onclick();await tick();assert(f.el('picker').open);assert.equal(f.el('picker-path').title,'/Review');
 const finish=f.delay();const selection=f.el('picker-items').children[0].onclick();f.el('remove').onclick();finish();await selection;
 assert(f.el('summary').hidden);assert.equal(f.el('filename').textContent,'');
 assert(!f.calls.some(x=>/\/(start|chunk|finish)/.test(x)));
 f=await fixture();await f.el('choose').onclick();await tick();await f.el('picker-items').children[0].onclick();
 assert.equal(f.el('filename').textContent,'Art.psd');assert(f.el('detail').textContent.includes('/Review/Art.psd'));
 f.el('remove').onclick();assert(f.el('summary').hidden);
 f.el('manual').onclick();for(const mode of ['DRAFT','LIVE','UPDATE']){f.el('mode').value=mode;await f.el('copy').onclick();assert.equal(f.el('copy').textContent,'Copied');}
 f=await fixture();const loaded=f.delayBrowse();f.el('choose').onclick();await tick();assert(f.el('picker').open);f.el('product').value='Retain product form';f.el('picker-close').onclick();assert(!f.el('picker').open);assert(f.el('choose').focused);loaded();await tick();assert.equal(f.el('picker-items').children.length,0);assert.equal(f.el('product').value,'Retain product form');
 f.el('choose').onclick();await tick();assert(f.el('picker').open);let prevented=false;f.el('picker').cancel({preventDefault:()=>{prevented=true}});assert(prevented&&!f.el('picker').open&&f.el('choose').focused);
 f=await fixture();f.failPreparation(true);f.el('choose').onclick();await tick();await f.el('picker-items').children[0].onclick();assert.equal(f.el('stage').textContent,'Error');assert.equal(f.el('error').textContent,'Original PSD download interrupted.');assert(!f.el('artwork-retry').hidden);f.failPreparation(false);await f.el('artwork-retry').onclick();assert.equal(f.el('stage').textContent,'Ready');assert(f.el('artwork-retry').hidden);assert(f.el('error').hidden);
 f=await fixture();const late=f.delayPreparation();f.el('choose').onclick();await tick();const old=f.el('picker-items').children[0].onclick();await tick();f.el('choose').onclick();await tick();await f.el('picker-items').children[0].onclick();const newest=f.metrics.selections.filter(x=>x.selection_to_mockup_ready_ms!==undefined).at(-1).id;late();await old;assert.equal(f.metrics.selections.filter(x=>x.selection_to_mockup_ready_ms!==undefined).at(-1).id,newest);
 console.log('PASS: exact ID/revision picker; stale response ignored; remove/fresh page empty; three prompt modes; no PSD byte transfer');
})().catch(e=>{console.error(e);process.exitCode=1});
