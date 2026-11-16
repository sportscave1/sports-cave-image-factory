const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function harness(crypto,textItem=true,options={}){
 let now=0,next=1;const timers=new Map(),events={},elements=new Map();
 class Element{
  constructor(){this.children=[];this.disabled=false;this.isConnected=true;this.html='';this.dataset={};this.style={setProperty(){}};}
  set textContent(v){this.html=v;this.children=[];}get textContent(){return this.html;}
  set innerHTML(v){this.html=v;}get innerHTML(){return this.html;}
  set id(v){elements.set(v,this);}append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}setAttribute(k,v){(this.attributes??={})[k]=v;}addEventListener(){}
  getBoundingClientRect(){return {height:60,width:120};}
 }
 const root=new Element();elements.set('root',root);
 const writes=[];let failure=false,pending=null;
 const clipboard={async writeText(text){writes.push(text);if(pending)await pending;if(failure)throw Error('denied');},async write(items){const data=items[0].data;writes.push(data['text/plain']?await data['text/plain'].text():await data['image/png']);if(pending)await pending;if(failure)throw Error('denied');}};
 const parent={postMessage(){},navigator:{clipboard},document:{hasFocus:()=>options.focused!==false}};
 const bridgeReplies=new Set(),requests=[],popups=[],session=new Map();
 const ctx={document:{getElementById:id=>elements.get(id),createElement:()=>new Element(),body:new Element()},parent,location:{origin:'https://fixture.test'},navigator:{clipboard},
  URL,AbortController,Blob,ClipboardItem:textItem?class{constructor(data){this.data=data;}}:undefined,fetch:async()=>({ok:true,blob:async()=>({type:'image/png',originalPixels:true})}),
  requestAnimationFrame:fn=>fn(),queueMicrotask,ResizeObserver:class{observe(){}},addEventListener:(type,fn)=>events[type]=fn,
  sessionStorage:{getItem:key=>session.get(key),setItem:(key,value)=>session.set(key,value)},
  setTimeout:(fn,delay)=>{const id=next++;timers.set(id,{fn,at:now+delay});return id;},clearTimeout:id=>timers.delete(id)};
 const window=ctx.window={ClipboardItem:ctx.ClipboardItem,frameElement:{},addEventListener:(_type,fn)=>bridgeReplies.add(fn),removeEventListener:(_type,fn)=>bridgeReplies.delete(fn),
  postMessage(message,origin){requests.push(message);for(const reply of bridgeReplies)reply({source:window,origin,data:{...message,direction:'response',result:options.companion}});},
  open(){return options.blockPopups ? null : {location:{replace:project=>popups.push(project)}};}};
 if(crypto){ctx.crypto=crypto;ctx.TextEncoder=TextEncoder;}
 vm.runInNewContext(fs.readFileSync('components/product_upload_gallery/app.js','utf8'),ctx);
 const render=(prompt,handoff)=>events.message({source:parent,data:{type:'streamlit:render',args:{mode:'actions',prompt,original:'/original.png',handoff}}});
 const tick=ms=>{now+=ms;for(const [id,t] of timers)if(t.at<=now){timers.delete(id);t.fn();}};
 return {elements,events,timers,writes,requests,popups,render,tick,fail:v=>failure=v,pending:v=>pending=v};
}
(async()=>{
 const h=harness();h.render('Unchanged master prompt');const prompt=h.elements.get('copyPrompt'),image=h.elements.get('copyImage');
 let resolve;h.pending(new Promise(r=>resolve=r));const copying=prompt.onclick();
 assert.equal(prompt.style.minWidth,'120px');
 assert.equal(prompt.textContent,'Copying…');assert.equal(h.timers.size,0);resolve();await copying;h.pending(null);
 assert.equal(prompt.attributes['aria-label'],'Copy Black Frame Prompt');assert.equal(image.attributes['aria-label'],'Copy black frame');
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
 const project='https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project';
 const workflow={project,companion_id:'a'.repeat(64),prompt:full,automatic:true};
 const edge=harness(require('node:crypto').webcrypto,true,{companion:{accepted:true}});
 const flush=()=>new Promise(resolve=>setImmediate(resolve));
 edge.render('manual copy', {pending:true});await flush();assert.equal(edge.requests.length,0);
 edge.pending(new Promise(()=>{}));
 edge.render('manual copy',workflow);await flush();
 assert.equal(edge.requests.length,1);assert.equal(edge.requests[0].prompt,full);
 assert.match(edge.elements.get('status').textContent,/sent to the Edge companion/);
 assert.equal(edge.writes[0],full);assert.deepEqual(edge.popups,[]);
 edge.render('manual copy after rerender',workflow);await flush();assert.equal(edge.requests.length,1);
 const background=harness(require('node:crypto').webcrypto,true,{companion:{accepted:true},focused:false});
 background.render('manual copy',workflow);await flush();assert.equal(background.requests.length,1);assert.equal(background.writes.length,0);
 const rejected=harness(require('node:crypto').webcrypto,true,{companion:{accepted:false},blockPopups:true});
 rejected.render('manual copy',workflow);await flush();assert.equal(rejected.writes[0],full);
 assert.equal(rejected.elements.get('status').children[0].href,project);
 const manual=harness(require('node:crypto').webcrypto,true,{companion:{accepted:false}});
 manual.render('manual copy',{...workflow,automatic:false});await flush();assert.equal(manual.requests.length,0);
 await manual.elements.get('uploadToChat').onclick();assert.deepEqual(manual.popups,[project]);assert.equal(manual.writes[0],full);
 console.log('Copy feedback: success-only, 2000ms reset, independent timers, repeat clicks, rejection, original payloads, rerender and unmount cleanup passed.');
 console.log('Prompt proof: complete long Unicode payload, byte lengths, SHA-256, feedback preservation and stale render rejection passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
