// Component event/state regression tests; no browser or provider writes.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),{webcrypto}=require('crypto');
const tick=()=>new Promise(r=>setImmediate(r));
async function fixture(){
 const elements={},listeners={},calls=[];
 const el=id=>elements[id]??=( {value:id==='mode'?'DRAFT':'',hidden:true,textContent:'',files:[],children:[],addEventListener(n,f){this[n]=f},replaceChildren(...c){this.children=c},append(c){this.children.push(c)},select(){},close(){this.open=false},showModal(){this.open=true},click(){return this.onclick?.()}} );
 let delayed=null,resolveFinish,clipboardFails=false;
 const doc={hidden:false,body:{getBoundingClientRect:()=>({height:500})},getElementById:el,createElement:()=>el(Math.random()),addEventListener(n,f){listeners[n]=f},execCommand:()=>true};
 const ctx={document:doc,console,crypto:webcrypto,Blob,Uint8Array,AbortController,ResizeObserver:class{observe(){}},URL,Image:class{},queueMicrotask,
 setTimeout:(f,n)=>{const t=setTimeout(f,n);t.unref();return t},clearTimeout,
 navigator:{clipboard:{writeText:async()=>{if(clipboardFails)throw Error('denied')}}},location:{origin:'http://local'},
 fetch:async(url,options)=>{
  calls.push(url);let body=options.body&&typeof options.body==='string'?JSON.parse(options.body):{};
  let data;
  if(url.includes('/state'))data={enabled:true,upload:null};
  else if(url.endsWith('/start'))data={upload:{id:body.id,mode:body.mode,name:body.name,size:body.size,offset:0,state:'Uploading PSD'}};
  else if(url.includes('/chunk'))data={upload:{id:'test',mode:'DRAFT',name:'current.psd',size:128,offset:128,state:'Checking design'}};
  else if(url.endsWith('/finish')){if(delayed)await new Promise(r=>resolveFinish=r);data={upload:{id:'test',mode:'DRAFT',name:'current.psd',size:128,offset:128,state:'Uploaded',basic_validated:true}};}
  else if(url.endsWith('/prompt'))data={prompt:'Selected '+body.mode};
  else if(url.endsWith('/copied'))data={upload:{id:'test',mode:body.mode,name:'current.psd',size:128,state:'Uploaded',basic_validated:true,copied:true}};
  else data={upload:null};
  return {ok:true,json:async()=>data};
 }};
 ctx.window=ctx;ctx.parent=ctx;ctx.addEventListener=(n,f)=>listeners[n]=f;ctx.postMessage=()=>{};
 vm.runInNewContext(fs.readFileSync('components/product_uploads/app.js','utf8'),ctx);await tick();
 return {el,calls,listeners,delay(){delayed=true},release(){resolveFinish()},denyClipboard(){clipboardFails=true}};
}
const file={name:'current.psd',size:128,slice:()=>new Blob([new Uint8Array(128)])};
(async()=>{
 let f=await fixture();assert.equal(f.el('mode').disabled,false);assert.equal(f.el('summary').hidden,true);assert.equal(f.el('return').hidden,true);
 for(const mode of ['DRAFT','LIVE','UPDATE']){f.el('mode').value=mode;await f.el('mode').onchange();assert.equal(f.el('action-label').textContent,{DRAFT:'Upload to Draft',LIVE:'Upload to Live',UPDATE:'Update Existing'}[mode]);}
 f.el('mode').value='DRAFT';f.el('file').files=[file];await f.el('file').onchange();assert.equal(f.el('summary').hidden,false);assert.equal(f.el('return').hidden,true);
 f.denyClipboard();await f.el('copy').onclick();assert.equal(f.el('fallback').open,true);assert.equal(f.el('return').hidden,true);
 await f.el('fallback-copy').onclick();assert.equal(f.el('return').hidden,false);
 f.el('remove').onclick();assert.equal(f.el('summary').hidden,true);assert.equal(f.el('return').hidden,true);assert.equal(f.el('product').value,'');
 f=await fixture();f.delay();f.el('file').files=[file];const running=f.el('file').onchange();
 while(!f.calls.some(c=>c.endsWith('/finish')))await tick();
 f.el('remove').onclick();f.release();await running;assert.equal(f.el('summary').hidden,true);assert.equal(f.el('prompt').hidden,true);
 assert.equal(f.el('preview').textContent,'Preview pending');
 f=await fixture();f.el('file').files=[{...file,name:'fake.jpg'}];await f.el('file').onchange();assert(!f.calls.some(c=>c.endsWith('/start')));assert(f.el('error').textContent.includes('PSD'));
 console.log('PASS: fresh state; three modes; PSD only; clipboard fallback; removal; late upload ignored');
})().catch(e=>{console.error(e);process.exitCode=1});
