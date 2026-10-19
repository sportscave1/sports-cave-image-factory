const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const flush=()=>new Promise(r=>setImmediate(r));
function setup(){
 const els={},timers=new Map(),calls=[];let clock=0,tid=0,state='Preparing',sequence=0,error='';
 class Element{constructor(){this.children=[];this.innerHTML='Copy all WEBP files';this.textContent=this.innerHTML;this.dataset={};this.disabled=false;}click(){}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=x;}setAttribute(){}}
 const el=id=>els[id]??=new Element();
 const ctx={document:{getElementById:el,createElement:()=>new Element()},performance:{now:()=>clock},addEventListener(){},setTimeout:(f,n)=>{const id=++tid;timers.set(id,{f,at:clock+n});return id;},clearTimeout:id=>timers.delete(id)};ctx.window=ctx;
 vm.runInNewContext(fs.readFileSync('components/product_uploads/package.js','utf8'),ctx);
 const pack={version:'v1',items:Array.from({length:8},(_,i)=>({name:i+'.webp',label:'Role '+i,preview:'/thumb/'+i,original:'/original/'+i}))};
 const api=ctx.ProductUploadPackage({resize(){},request:async(path,body)=>{calls.push({path,body});if(path==='clipboard-launch')return {code:'session',url:'sports-cave-files://webp#session'};if(path==='clipboard-status'){if(body.copy){state='CopyRequested';sequence++;}return {state,count:8,sequence,error,copy_ms:30};}return pack;}});
 return {api,el,calls,timers,state:s=>state=s,error:e=>error=e,tick:async n=>{clock+=n;for(const [id,t] of [...timers])if(t.at<=clock){timers.delete(id);t.f();}await flush();}};
}
(async()=>{
 const h=setup();await h.api.sync({id:'upload',saved_package_version:'saved'},true);await flush();
 assert.equal(h.el('saved-files').children.length,8);assert.equal(h.el('copy-files').disabled,true);
 assert.equal(h.calls.filter(x=>x.body?.copy).length,0);assert.ok(!h.calls.some(x=>x.path.startsWith('/original')));
 h.state('Ready');await h.tick(750);assert.equal(h.el('copy-files').disabled,false);
 for(let i=0;i<3;i++){
  await h.el('copy-files').onclick();await h.el('copy-files').onclick();assert.equal(h.calls.filter(x=>x.body?.copy).length,i+1);
  h.state('Complete');await h.tick(750);assert.equal(h.el('copy-files').textContent,'Copied 8 files ✓');
  await h.tick(2000);assert.equal(h.el('copy-files').innerHTML,'Copy all WEBP files');
 }
 assert.equal(h.calls.filter(x=>x.path==='clipboard-launch').length,1);
 h.state('Failed');h.error('office.webp is missing');await h.tick(750);assert.match(h.el('package-error').textContent,/office.webp/);
 assert.equal(h.el('copy-files').textContent,'Retry file preparation');
 h.api.reset();assert.equal(h.timers.size,0);assert.equal(h.el('saved-files').children.length,0);assert.ok(h.calls.some(x=>x.body?.cancel));
 await h.api.sync({id:'new',saved_package_version:'new'},true);h.api.dispose();await flush();assert.equal(h.timers.size,0);
 console.log('Package UI: preparation without copying, 8 previews, repeated explicit copies, feedback reset, missing-file errors and unmount cancellation passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
