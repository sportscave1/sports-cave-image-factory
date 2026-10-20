const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function harness(){
 let now=0,next=1;const timers=new Map(),events={},elements=new Map();
 class Element{
  constructor(){this.children=[];this.disabled=false;this.html='';this.style={setProperty(){}};}
  set textContent(v){this.html=v;this.children=[];}get textContent(){return this.html;}
  set innerHTML(v){this.html=v;}get innerHTML(){return this.html;}
  set id(v){elements.set(v,this);}append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}setAttribute(k,v){(this.attributes??={})[k]=v;}addEventListener(){}
  getBoundingClientRect(){return {height:60,width:120};}
 }
 const root=new Element();elements.set('root',root);
 const writes=[];let failure=false,pending=null;
 const clipboard={async writeText(text){writes.push(text);if(pending)await pending;if(failure)throw Error('denied');},async write(items){writes.push(await items[0].data['image/png']);if(failure)throw Error('denied');}};
 const parent={postMessage(){}};
 const ctx={document:{getElementById:id=>elements.get(id),createElement:()=>new Element(),body:new Element()},parent,location:{origin:'https://fixture.test'},navigator:{clipboard},
  URL,AbortController,ClipboardItem:class{constructor(data){this.data=data;}},fetch:async()=>({ok:true,blob:async()=>({type:'image/png',originalPixels:true})}),
  requestAnimationFrame:fn=>fn(),ResizeObserver:class{observe(){}},addEventListener:(type,fn)=>events[type]=fn,
  setTimeout:(fn,delay)=>{const id=next++;timers.set(id,{fn,at:now+delay});return id;},clearTimeout:id=>timers.delete(id)};
 ctx.window=ctx;
 vm.runInNewContext(fs.readFileSync('components/product_upload_gallery/app.js','utf8'),ctx);
 const render=prompt=>events.message({source:parent,data:{type:'streamlit:render',args:{mode:'actions',prompt,original:'/original.png'}}});
 const tick=ms=>{now+=ms;for(const [id,t] of timers)if(t.at<=now){timers.delete(id);t.fn();}};
 return {elements,events,timers,writes,render,tick,fail:v=>failure=v,pending:v=>pending=v};
}
(async()=>{
 const h=harness();h.render('Unchanged master prompt');const prompt=h.elements.get('copyPrompt'),image=h.elements.get('copyImage');
 let resolve;h.pending(new Promise(r=>resolve=r));const copying=prompt.onclick();
 assert.equal(prompt.style.minWidth,'120px');
 assert.equal(prompt.textContent,'Copying…');assert.equal(h.timers.size,0);resolve();await copying;h.pending(null);
 assert.equal(prompt.attributes['aria-label'],'Copy prompt');assert.equal(image.attributes['aria-label'],'Copy black frame');
 assert.equal(prompt.title,'Prompt copied');
 assert.equal(prompt.style.minWidth,'120px');
 assert.equal(prompt.textContent,'Copied');h.tick(1000);await image.onclick();assert.equal(image.textContent,'Copied');
 h.tick(999);assert.equal(prompt.textContent,'Copied');h.tick(1);assert.equal(prompt.textContent,'Copy prompt');assert.equal(image.textContent,'Copied');
 h.tick(1000);assert.equal(image.textContent,'Copy black frame');
 assert.equal(prompt.title,'Copy prompt to clipboard');assert.equal(image.title,'Copy black frame to clipboard');
 assert.equal(prompt.style.minWidth,'');assert.equal(image.style.minWidth,'');
 await prompt.onclick();h.tick(1500);await prompt.onclick();h.tick(500);assert.equal(prompt.textContent,'Copied');h.tick(1500);assert.equal(prompt.textContent,'Copy prompt');
 h.fail(true);await prompt.onclick();assert.equal(prompt.textContent,'Copy prompt');assert.match(h.elements.get('status').textContent,/Could not copy prompt/);assert.equal(h.timers.size,0);
 assert.equal(prompt.title,'Copy prompt to clipboard');
 assert.equal(prompt.style.minWidth,'');
 await image.onclick();assert.equal(image.textContent,'Copy black frame');assert.match(h.elements.get('status').textContent,/Could not copy image/);
 h.fail(false);await prompt.onclick();await image.onclick();assert.equal(h.timers.size,2);h.render('new master');assert.equal(h.timers.size,0);
 await h.elements.get('copyPrompt').onclick();h.events.pagehide();assert.equal(h.timers.size,0);
 assert.equal(h.writes[0],'Unchanged master prompt');assert(h.writes.some(w=>w.originalPixels));
 console.log('Copy feedback: success-only, 2000ms reset, independent timers, repeat clicks, rejection, original payloads, rerender and unmount cleanup passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
