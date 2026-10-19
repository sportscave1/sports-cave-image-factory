const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),{webcrypto,createHash}=require('node:crypto');
const bytes=Buffer.from('UklGRjwAAABXRUJQVlA4IDAAAADQAQCdASoQAAwAAUAmJaACdLoB+AADsAD+8ut//NgVzXPv9//S4P0uD9Lg/9KQAAA=','base64');
const hash=b=>createHash('sha256').update(createHash('sha256').update(b).digest()).digest('hex');
function setup(){
 const els={},timers=new Map(),calls=[],fetches=[],downloads=[],urls=new Map();let tid=0,clock=0,wait=null,body=bytes,mime='image/webp';
 class Element{constructor(){this.children=[];this.textContent='';this.disabled=false;}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=x;}setAttribute(){}remove(){}click(){if(this.download)downloads.push({name:this.download,blob:urls.get(this.href)});}}
 const el=id=>els[id]??=new Element();
 const ctx={AbortController,Blob,Date,Uint8Array,DataView,crypto:webcrypto,document:{body:new Element(),getElementById:el,createElement:()=>new Element()},
  URL:{createObjectURL:blob=>{const u='blob:'+urls.size;urls.set(u,blob);return u;},revokeObjectURL:u=>urls.delete(u)},
  fetch:async(url,options)=>{fetches.push({url,options});if(wait)await wait;return {ok:true,blob:async()=>new Blob([body],{type:mime})};},
  navigator:{clipboard:{write(){throw Error('Image clipboard must never be called');}}},
  addEventListener(){},setTimeout:(f,n)=>{const id=++tid;timers.set(id,{f,at:clock+n});return id;},clearTimeout:id=>timers.delete(id)};ctx.window=ctx;
 vm.runInNewContext(fs.readFileSync('components/product_uploads/package.js','utf8'),ctx);
 const pack={version:'v1',items:Array.from({length:8},(_,i)=>({name:i+'.webp',label:'Role '+i,preview:'/thumb/'+i,original:'/original/'+i,download:'/download/'+i,size:bytes.length,content_hash:hash(bytes)}))};
 const api=ctx.ProductUploadPackage({resize(){},request:async(path,body)=>{calls.push({path,body});return pack;}});
 return {api,el,calls,fetches,downloads,timers,urls,pack,buttons:()=>el('saved-files').children.map(c=>c.children[2]),copies:()=>el('saved-files').children.map(c=>c.children[1]),status:i=>el('saved-files').children[i].children[5],data:(b,m='image/webp')=>{body=b;mime=m;},delay:()=>{let done;wait=new Promise(r=>done=r);return done;},tick:n=>{clock+=n;for(const [id,t] of [...timers])if(t.at<=clock){timers.delete(id);t.f();}}};
}
(async()=>{
 const h=setup();await h.api.sync({id:'upload',saved_package_version:'saved'},true);assert.equal(h.fetches.length,0);assert.equal(h.el('saved-files').children.length,8);
 assert(h.copies().every(b=>b.disabled&&b.textContent==='Copy unavailable'));
 for(let i=0;i<8;i++){await h.buttons()[i].onclick();assert.equal(h.fetches[i].url,'/download/'+i);assert.equal(h.downloads[i].name,i+'.webp');assert.equal(h.downloads[i].blob.type,'image/webp');assert.deepEqual(Buffer.from(await h.downloads[i].blob.arrayBuffer()),bytes);}
 h.tick(1999);assert.equal(h.buttons()[0].textContent,'Download started');h.tick(1);assert.equal(h.buttons()[0].textContent,'Download WEBP');
 await h.buttons()[0].onclick();assert.equal(h.fetches.length,8);h.tick(1000);await h.buttons()[1].onclick();h.tick(1000);assert.equal(h.buttons()[0].textContent,'Download WEBP');assert.equal(h.buttons()[1].textContent,'Download started');h.api.dispose();assert.equal(h.timers.size,0);assert.equal(h.urls.size,0);
 for(const defect of ['mime','signature','hash','size','name']){
  const bad=setup();if(defect==='mime')bad.data(bytes,'image/png');if(defect==='signature'){const b=Buffer.from(bytes);b[0]=0;bad.data(b);}if(defect==='hash'){const b=Buffer.from(bytes);b[b.length-1]^=1;bad.data(b);}if(defect==='size')bad.pack.items[0].size++;if(defect==='name')bad.pack.items[0].name='../other.webp';
  await bad.api.sync({id:'upload',saved_package_version:'saved'},true);await bad.buttons()[0].onclick();assert.equal(bad.downloads.length,0,defect);assert(bad.status(0).textContent,defect);assert(!bad.buttons()[0].disabled);bad.api.dispose();
 }
 const stale=setup();await stale.api.sync({id:'old',saved_package_version:'saved'},true);const finish=stale.delay();const button=stale.buttons()[0],old=button.onclick();await button.onclick();assert.equal(stale.fetches.length,1);await stale.api.sync({id:'new',saved_package_version:'new'},true);finish();await old;assert.equal(stale.downloads.length,0);assert(stale.calls.every(x=>x.path.startsWith('saved-package?')));
 console.log('PASS: exact WEBP bytes/name/MIME; signature, hash and size rejection; eight lazy downloads; cache; independent timers; duplicates; stale selection; cleanup; zero image clipboard/helper calls.');
})().catch(e=>{console.error(e);process.exitCode=1;});
