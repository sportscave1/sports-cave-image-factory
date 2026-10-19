const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const flush=()=>new Promise(r=>setImmediate(r));
function setup(webp=false){
 const els={},timers=new Map(),calls=[],fetches=[],writes=[],events={};let clock=0,tid=0,delay=null,deny=false;
 class Element{constructor(){this.children=[];this.textContent='';this.disabled=false;}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=x;}setAttribute(){}getContext(){return {drawImage(){}};}toBlob(fn){fn({type:'image/png',width:this.width,height:this.height});}}
 const el=id=>els[id]??=new Element();
 const ctx={AbortController,Date,document:{getElementById:el,createElement:()=>new Element()},isSecureContext:true,
  ClipboardItem:class{static supports(t){return webp&&t==='image/webp';}constructor(data){this.data=data;}},
  navigator:{clipboard:{write:async items=>{const data=items[0].data;const type=Object.keys(data)[0];const blob=await data[type];if(deny)throw Error('Denied');writes.push({type,blob});}}},
  createImageBitmap:async blob=>({width:2400,height:1600,close(){}}),
  fetch:async(url,options)=>{fetches.push({url,options});if(delay)await delay;return {ok:true,blob:async()=>({type:'image/webp',size:100,url})};},
  addEventListener:(n,f)=>events[n]=f,setTimeout:(f,n)=>{const id=++tid;timers.set(id,{f,at:clock+n});return id;},clearTimeout:id=>timers.delete(id)};ctx.window=ctx;
 vm.runInNewContext(fs.readFileSync('components/product_uploads/package.js','utf8'),ctx);
 const pack={version:'v1',items:Array.from({length:8},(_,i)=>({name:i+'.webp',label:'Role '+i,preview:'/thumb/'+i,original:'/original/'+i}))};
 const api=ctx.ProductUploadPackage({resize(){},request:async(path,body)=>{calls.push({path,body});return pack;}});
 return {api,el,calls,fetches,writes,timers,events,buttons:()=>el('saved-files').children.map(c=>c.children[1]),status:i=>el('saved-files').children[i].children[4],deny:()=>deny=true,
  delay:()=>{let done;delay=new Promise(r=>done=r);return done;},tick:n=>{clock+=n;for(const [id,t] of [...timers])if(t.at<=clock){timers.delete(id);t.f();}}};
}
(async()=>{
 const h=setup();await h.api.sync({id:'upload',saved_package_version:'saved'},true);
 assert.equal(h.el('saved-files').children.length,8);assert.equal(h.fetches.length,0);assert.equal(h.timers.size,0);
 const buttons=h.buttons();
 for(let i=0;i<8;i++){await buttons[i].onclick();assert.equal(buttons[i].textContent,'Copied ✓');assert.equal(h.fetches[i].url,'/original/'+i);assert.equal(h.writes[i].type,'image/png');assert.equal(h.writes[i].blob.width,2400);assert.equal(h.writes[i].blob.height,1600);}
 assert.match(h.status(0).textContent,/PNG/);h.tick(1999);assert.equal(buttons[0].textContent,'Copied ✓');h.tick(1);assert.equal(buttons[0].textContent,'Copy');
 await buttons[0].onclick();assert.equal(h.fetches.length,8,'reuse pinned original');h.tick(1000);await buttons[1].onclick();h.tick(1000);assert.equal(buttons[0].textContent,'Copy');assert.equal(buttons[1].textContent,'Copied ✓');
 const done=h.delay();const pending=buttons[2].onclick();assert.equal(buttons[2].textContent,'Copying…');await buttons[2].onclick();h.api.reset();done();await pending;
 assert.equal(h.timers.size,0);assert.equal(h.el('saved-files').children.length,0);
 assert(h.calls.every(x=>x.path.startsWith('saved-package?')),'no companion calls');
 const w=setup(true);await w.api.sync({id:'upload',saved_package_version:'saved'},true);await w.buttons()[0].onclick();assert.equal(w.writes[0].type,'image/webp');assert.equal(w.writes[0].blob.url,'/original/0');
 w.deny();await w.buttons()[1].onclick();assert.equal(w.buttons()[1].textContent,'Copy');assert.equal(w.buttons()[1].disabled,false);w.api.dispose();assert.equal(w.timers.size,0);
 const stale=setup();await stale.api.sync({id:'old',saved_package_version:'saved'},true);const finish=stale.delay();const old=stale.buttons()[0].onclick();await stale.api.sync({id:'new',saved_package_version:'new'},true);finish();await old;assert.equal(stale.writes.length,0,'stale retrieval never reaches clipboard');
 console.log('PASS: eight lazy original sources; full dimensions; PNG and native WEBP; cache; independent 2s timers; duplicate clicks; denial; stale selection; disposal; zero helper requests.');
})().catch(e=>{console.error(e);process.exitCode=1;});
