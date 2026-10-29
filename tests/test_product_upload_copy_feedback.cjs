const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function harness(crypto,textItem=true){
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
 const clipboard={async writeText(text){writes.push(text);if(pending)await pending;if(failure)throw Error('denied');},async write(items){const data=items[0].data;writes.push(data['text/plain']?await data['text/plain'].text():await data['image/png']);if(pending)await pending;if(failure)throw Error('denied');}};
 const parent={postMessage(){}};
 const ctx={document:{getElementById:id=>elements.get(id),createElement:()=>new Element(),body:new Element()},parent,location:{origin:'https://fixture.test'},navigator:{clipboard},
  URL,AbortController,Blob,ClipboardItem:textItem?class{constructor(data){this.data=data;}}:undefined,fetch:async()=>({ok:true,blob:async()=>({type:'image/png',originalPixels:true})}),
  requestAnimationFrame:fn=>fn(),ResizeObserver:class{observe(){}},addEventListener:(type,fn)=>events[type]=fn,
  setTimeout:(fn,delay)=>{const id=next++;timers.set(id,{fn,at:now+delay});return id;},clearTimeout:id=>timers.delete(id)};
 ctx.window=ctx;if(crypto){ctx.crypto=crypto;ctx.TextEncoder=TextEncoder;}
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
 const proofHarness=harness(require('node:crypto').webcrypto),full='Long prompt 🖼\r\n'.repeat(3000);
 proofHarness.render(full);await new Promise(r=>setTimeout(r,30));
 const proved=proofHarness.elements.get('copyPrompt');
 const proof=JSON.parse(proved.recorderPromptProof);
 assert.equal(proof.sha256,require('node:crypto').createHash('sha256').update(full).digest('hex'));
 assert.equal(proof.utf16_length,full.length);assert.equal(proof.utf8_length,Buffer.byteLength(full));
 assert.equal(proved.attributes['aria-label'],'Copy Black Frame Prompt');
 await proved.onclick();assert.equal(proofHarness.writes[0],full);assert.match(proved.title,/^Prompt copied\nSports Cave prompt v1: /);
 proofHarness.tick(2000);assert.match(proved.title,/^Copy prompt to clipboard\nSports Cave prompt v1: /);
 let finish;const stale=harness({subtle:{digest:()=>new Promise(r=>finish=r)}});stale.render('old');const old=stale.elements.get('copyPrompt');stale.render('');finish(new Uint8Array(32).buffer);await Promise.resolve();
 assert.equal(old.recorderPromptProof,undefined);assert.equal(stale.elements.get('copyPrompt').recorderPromptProof,undefined);
 const fallback=harness(undefined,false);fallback.render(full);await fallback.elements.get('copyPrompt').onclick();assert.equal(fallback.writes[0],full);assert.equal(fallback.elements.get('copyPrompt').title,'Prompt copied');
 console.log('Copy feedback: success-only, 2000ms reset, independent timers, repeat clicks, rejection, original payloads, rerender and unmount cleanup passed.');
 console.log('Prompt proof: complete long Unicode payload, byte lengths, SHA-256, feedback preservation and stale render rejection passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
