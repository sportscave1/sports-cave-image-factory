const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),{webcrypto}=require('node:crypto');
const flush=()=>new Promise(r=>setImmediate(r));
function setup(){
 const els={},listeners=new Set(),timers=new Map(),calls=[],nativeCalls=[];let clock=0,tid=0,count=8,error='',delay=false,respond,connected=true;
 class Element{constructor(){this.children=[];this.innerHTML='Copy all WEBP files';this.textContent=this.innerHTML;this.disabled=false;}append(...items){this.children.push(...items);}replaceChildren(...items){this.children=items;}setAttribute(){}}
 const el=id=>els[id]??=new Element();
 const bridge={addEventListener:(t,f)=>listeners.add(f),removeEventListener:(t,f)=>listeners.delete(f),postMessage:m=>{
  nativeCalls.push(m);if(m.action==='cancel')return;
  const reply=()=>{for(const f of [...listeners])f({data:{type:'sports-cave-desktop',request_id:m.request_id,action:m.action==='hello'?'capabilities':m.action,ok:!error,productUploadWebp:true,count,message:error}});};
  if(delay&&m.action!=='hello')respond=reply;else queueMicrotask(reply);
 }};
 const ctx={document:{getElementById:el,createElement:()=>new Element()},crypto:webcrypto,addEventListener(){},
  setTimeout:(f,n)=>{const id=++tid;timers.set(id,{f,at:clock+n});return id;},clearTimeout:id=>timers.delete(id)};
 ctx.window=ctx;ctx.top={get chrome(){return connected?{webview:bridge}:undefined;}};
 vm.runInNewContext(fs.readFileSync('components/product_uploads/package.js','utf8'),ctx);
 const pack={version:'v1',items:Array.from({length:8},(_,i)=>({name:i+'.webp',role:''+i,label:'Role '+i,preview:'/thumb/'+i,original:'/original/'+i,download:'/download/'+i}))};
 const api=ctx.ProductUploadPackage({resize(){},request:async(path,body)=>{calls.push({path,body});return body?{transfer:{ticket:'ticket',secret:'fixture',base_url:'http://fixture'}}:pack;}});
 return {api,els,el,calls,nativeCalls,timers,respond:()=>respond(),delay:v=>delay=v,connect:v=>connected=v,error:v=>error=v,count:v=>count=v,
  tick:n=>{clock+=n;for(const [id,t] of [...timers])if(t.at<=clock){timers.delete(id);t.f();}}};
}
(async()=>{
 const h=setup();await h.api.sync({id:'upload',saved_package_version:'saved'},true,'save1');assert.equal(h.el('saved-files').children.length,8);
 assert.equal(h.calls.length,1);assert.ok(h.calls[0].path.startsWith('saved-package')); // No originals during rendering.
 await h.el('copy-files').onclick();assert.equal(h.el('copy-files').textContent,'Copied');assert.equal(h.calls[1].body.version,'v1');
 h.tick(1500);await h.el('copy-files').onclick();h.tick(1500);assert.equal(h.el('copy-files').textContent,'Copied');h.tick(500);assert.equal(h.el('copy-files').innerHTML,'Copy all WEBP files');
 h.error('office.webp: unreadable');await h.el('copy-files').onclick();assert.match(h.el('package-error').textContent,/office.webp/);assert.equal(h.el('copy-files').innerHTML,'Copy all WEBP files');
 h.error('');h.count(7);await h.el('copy-files').onclick();assert.match(h.el('package-error').textContent,/every saved WebP/);
 h.count(8);h.delay(true);const pending=h.el('copy-files').onclick();await flush();h.api.reset();h.respond();await pending;assert.equal(h.el('saved-package').hidden,true);assert.ok(h.nativeCalls.some(x=>x.action==='cancel'));assert.equal(h.timers.size,0);
 const browser=setup();browser.connect(false);await browser.api.sync({id:'upload',saved_package_version:'saved'},true,'save');await browser.el('copy-files').onclick();assert.equal(browser.el('file-fallback').hidden,false);assert.match(browser.el('package-error').textContent,/Windows desktop/);await browser.el('select-files').onclick();assert.equal(browser.el('attachment-files').children.length,8);assert.equal(browser.calls.length,1);browser.api.dispose();
 console.log('Saved package: eight receipt files, no original prefetch, native count verification, 2-second restart, errors/retry, offline fallback and stale/unmount cancellation passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
