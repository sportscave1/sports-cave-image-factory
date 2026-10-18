// Component event/state regression tests; no browser or provider writes.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),{webcrypto}=require('crypto');
const tick=()=>new Promise(r=>setImmediate(r));
async function fixture(options={}){
 const config=options;
 const elements={},listeners={},calls=[],starts=[],progressStates=[],deadlines=[];
 let now=0,timerID=0;const virtualTimers=new Map();
 const schedule=(f,n)=>{if(config.clock){const id=++timerID;virtualTimers.set(id,{at:now+n,f});return id;}const t=setTimeout(f,options.fastRetry&&n<=30000?0:n);if(n>30000||!options.fastRetry)t.unref();return t;};
 const cancelTimer=id=>config.clock?virtualTimers.delete(id):clearTimeout(id);
 const advance=async ms=>{const end=now+ms;for(;;){const next=[...virtualTimers.entries()].filter(([,v])=>v.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!next){now=end;await tick();break;}virtualTimers.delete(next[0]);now=next[1].at;next[1].f();await tick();}};
 const el=id=>elements[id]??=( {value:id==='mode'?'DRAFT':'',hidden:true,textContent:'',files:[],children:[],addEventListener(n,f){this[n]=f},replaceChildren(...c){this.children=c},append(c){this.children.push(c)},select(){},close(){this.open=false},showModal(){this.open=true},click(){return this.onclick?.()}} );
 let delayed=null,resolveFinish,clipboardFails=false,currentID='test',offset=0,size=128,chunkFailures=options.chunkFailures||0,finishFailures=options.finishFailures||0,chunkNumber=0;const stored=options.stored||new Map();let resumeBusy=options.resumeBusy||0;
 const doc={hidden:false,body:{getBoundingClientRect:()=>({height:500})},getElementById:el,createElement:()=>el(Math.random()),addEventListener(n,f){listeners[n]=f},execCommand:()=>true};
 const ctx={sessionStorage:{getItem:k=>stored.get(k),setItem:(k,v)=>stored.set(k,v),removeItem:k=>stored.delete(k)},Date:config.clock?{now:()=>now}:Date,Number,document:doc,console,crypto:webcrypto,Blob,Uint8Array,AbortController,ResizeObserver:class{observe(){}},URL,URLSearchParams,Image:class{},queueMicrotask,
 setTimeout:schedule,clearTimeout:cancelTimer,
 navigator:{clipboard:{writeText:async()=>{if(clipboardFails)throw Error('denied')}}},location:{origin:'http://local'},
 fetch:async(url,options)=>{
  calls.push(url);let body=options.body&&typeof options.body==='string'?JSON.parse(options.body):{};
  let data;
  if(url.includes('/state'))data={enabled:true,upload:null};
  else if(url.endsWith('/start')){starts.push(body);currentID=body.id;size=body.size;data={upload:{id:body.id,mode:body.mode,name:body.name,size,offset,transport_chunk_bytes:config.transport,relay_resume:config.relayResume,state:'Uploading PSD'}};}
  else if(url.includes('/chunk')){
   chunkNumber++;const at=Number(url.split('offset=')[1]);
   if(chunkFailures>0&&(config.failAfter===undefined||chunkNumber>config.failAfter)){chunkFailures--;return {ok:false,status:503,json:async()=>({error:'temporary chunk failure'})};}
   offset=Math.max(offset,at+options.body.size);data={upload:{id:currentID,mode:'DRAFT',name:'current.psd',size,offset,transport_chunk_bytes:config.transport,relay_resume:config.relayResume,state:offset===size?'Checking design':'Uploading PSD'}};
  }
  else if(url.endsWith('/resume')){if(resumeBusy-->0)return {ok:false,status:503,json:async()=>({error:'settling'})};data={upload:{id:currentID,mode:'DRAFT',name:'current.psd',size,offset,transport_chunk_bytes:config.transport,relay_resume:config.relayResume,state:'Uploading PSD'}};}
  else if(url.endsWith('/finish')){if(finishFailures-->0)return {ok:false,status:503,json:async()=>({error:'temporary finish failure'})};if(delayed)await new Promise(r=>resolveFinish=r);data={upload:{id:currentID,mode:'DRAFT',name:'current.psd',size,offset:size,state:'Uploaded',basic_validated:true}};}
  else if(url.endsWith('/prompt'))data={prompt:'Selected '+body.mode};
  else if(url.endsWith('/copied'))data={upload:{id:'test',mode:body.mode,name:'current.psd',size:128,state:'Uploaded',basic_validated:true,copied:true}};
  else data={upload:null};
  return {ok:true,status:200,json:async()=>data};
 }};
 ctx.XMLHttpRequest=class{
  upload={};status=200;responseText='';
  open(method,url){this.url=url;}setRequestHeader(){}getResponseHeader(){return '';}abort(){for(const t of this.pending||[])cancelTimer(t);this.onabort?.();}
  async send(blob){
   calls.push(this.url);chunkNumber++;deadlines.push(this.timeout);
   if(config.progressive&&chunkNumber===1){
    this.pending=[];const finish=()=>{for(const t of this.pending)cancelTimer(t);offset=Math.max(offset,blob.size);this.responseText=JSON.stringify({upload:{id:currentID,mode:'DRAFT',name:'current.psd',size,offset,transport_chunk_bytes:config.transport,relay_resume:config.relayResume,state:'Checking design'}});this.onload();};
    this.pending.push(schedule(()=>this.ontimeout(),this.timeout));
    if(config.progressive==='continue'){
     for(let i=1;i<=5;i++)this.pending.push(schedule(()=>this.upload.onprogress?.({loaded:Math.floor(blob.size*i/5)}),45000*i));
     this.pending.push(schedule(finish,325000));
    }else this.pending.push(schedule(()=>{offset=4*1024*1024;this.upload.onprogress?.({loaded:offset});},1000));
    return;
   }
   this.upload.onprogress?.({loaded:blob.size});progressStates.push({stage:el('stage').textContent,detail:el('detail').textContent});
   const at=Number(this.url.split('offset=')[1]);
   if(chunkFailures>0&&(options.failAfter===undefined||chunkNumber>options.failAfter)){
    chunkFailures--;if(options.loseAck)offset=Math.max(offset,at+(options.partialAck||blob.size));
    if(options.timeout)this.ontimeout();else{this.status=options.failureStatus||503;this.responseText=JSON.stringify({error:'temporary chunk failure'});this.onload();}return;
   }
   offset=Math.max(offset,at+blob.size);this.responseText=JSON.stringify({upload:{id:currentID,mode:'DRAFT',name:'current.psd',size,offset,transport_chunk_bytes:config.transport,relay_resume:config.relayResume,state:offset===size?'Checking design':'Uploading PSD'}});this.onload();
  }
 };
 ctx.window=ctx;ctx.parent=ctx;ctx.addEventListener=(n,f)=>listeners[n]=f;ctx.postMessage=()=>{};
 vm.runInNewContext(config.source||fs.readFileSync('components/product_uploads/app.js','utf8'),ctx);await tick();
 return {el,calls,listeners,delay(){delayed=true},release(){resolveFinish()},denyClipboard(){clipboardFails=true},metrics:ctx.productUploadMetrics,stored,starts,progressStates,advance,deadlines};
}
const file={name:'current.psd',size:128,slice:(at,end)=>new Blob([new Uint8Array(Math.min(end,128)-at)])};
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
 // Transient ACK loss must retry the same offset, without hashing or creating again.
 f=await fixture({chunkFailures:2,loseAck:true,fastRetry:true,finishFailures:1});f.el('file').files=[file];await f.el('file').onchange();
 assert.equal(f.el('stage').textContent,'Uploaded',f.el('error').textContent);assert.equal(f.calls.filter(c=>c.endsWith('/start')).length,1);
 assert.equal(f.calls.filter(c=>c.includes('/chunk')).length,3);assert.equal(f.metrics.identity.length,1);
 assert.equal(f.calls.filter(c=>c.endsWith('/finish')).length,2);
 // Exhausted transient retries keep File access and offer Retry upload, then recover without reselect/hash.
 f=await fixture({chunkFailures:6,timeout:true,fastRetry:true});f.el('file').files=[file];await f.el('file').onchange();
 assert.equal(f.el('stage').textContent,'Interrupted');assert.equal(f.el('retry').hidden,false);assert.equal(f.el('retry').textContent,'Retry upload');
 assert(!f.el('detail').textContent.includes('Reselect'));await f.el('retry').onclick();assert.equal(f.el('stage').textContent,'Uploaded',f.el('error').textContent);assert.equal(f.metrics.identity.length,1);
 // Permanent validation failures must not be retried.
 f=await fixture({chunkFailures:1,failureStatus:409,fastRetry:true});f.el('file').files=[file];await f.el('file').onchange();assert.equal(f.calls.filter(c=>c.includes('/chunk')).length,1);
 // Refresh leaves an empty visible selection, yet explicit identical selection recovers the durable ID.
 const shared=new Map();f=await fixture({chunkFailures:6,fastRetry:true,stored:shared});f.el('file').files=[file];await f.el('file').onchange();
 const prior=JSON.parse([...shared.values()][0]).id;f=await fixture({stored:shared});assert.equal(f.el('summary').hidden,true);assert.equal(f.el('preview').children.length,0);
 f.el('file').files=[file];await f.el('file').onchange();assert.equal(f.el('stage').textContent,'Uploaded',f.el('error').textContent);
 assert.equal(f.starts[0].id,prior);
 assert.equal(shared.size,0); // successful finish clears resumable metadata
 // Another selection with identical name/size but different bytes cannot hijack an interrupted upload.
 f=await fixture({chunkFailures:6,fastRetry:true});f.el('file').files=[file];await f.el('file').onchange();
 f.el('file').files=[{...file,slice:(at,end)=>new Blob([new Uint8Array(Math.min(end,128)-at).fill(1)])}];await f.el('file').onchange();
 assert(f.el('error').textContent.includes('differs'));assert.equal(f.starts.length,1);
 await f.el('retry').onclick();assert.equal(f.el('stage').textContent,'Uploaded',f.el('error').textContent);
 // Automatic continuation passes 4 MiB without a page rerun or polling between chunks.
 const big={name:'large.psd',size:4*1024*1024+128,slice(at,end){return new Blob([new Uint8Array(Math.min(end,this.size)-at)])}};
 f=await fixture({chunkFailures:2,failAfter:1,fastRetry:true});f.el('file').files=[big];await f.el('file').onchange();
 const chunks=f.calls.filter(c=>c.includes('/chunk'));assert.equal(chunks.length,4);assert(chunks.slice(1).every(c=>c.endsWith('offset=4194304')));
 assert.equal(f.calls.filter(c=>c.includes('/state')).length,1);assert.equal(f.metrics.identity.length,1);
 assert(f.progressStates.every(s=>s.stage==='Uploading'&&!s.detail.includes('Reselect')));
 assert(f.progressStates.some(s=>s.detail.includes('MiB/s')));assert(f.progressStates.some(s=>s.detail.includes('MiB sent in this request')));
 // Reproduce the apparent 4 MiB stop in the old UI under four consecutive transient failures.
 const baseline=require('child_process').execFileSync('git',['show','5af8499e:components/product_uploads/app.js'],{encoding:'utf8'});
 const before=await fixture({source:baseline,chunkFailures:4,failAfter:1,fastRetry:true});before.el('file').files=[big];await before.el('file').onchange();
 assert(before.el('detail').textContent.includes('4.0 /'));assert(before.el('detail').textContent.includes('Reselect'));
 assert.equal(before.calls.filter(c=>c.includes('/chunk')).length,4); // first success + 3 failed attempts
 const after=await fixture({chunkFailures:4,failAfter:1,fastRetry:true});after.el('file').files=[big];await after.el('file').onchange();
 assert.equal(after.el('stage').textContent,'Uploaded',after.el('error').textContent);assert.equal(after.metrics.identity.length,1);
 // Negotiate 8 MiB ordered batches while preserving old-server fallback above.
 const batched={name:'batch.psd',size:12*1024*1024+128,slice(at,end){return new Blob([new Uint8Array(Math.min(end,this.size)-at)])}};
 f=await fixture({transport:8*1024*1024,chunkFailures:1,loseAck:true,fastRetry:true});f.el('file').files=[batched];await f.el('file').onchange();
 assert.equal(f.el('stage').textContent,'Uploaded',f.el('error').textContent);
 const batchCalls=f.calls.filter(c=>c.includes('/chunk'));assert.equal(batchCalls.length,3);
 assert(batchCalls[0].endsWith('offset=0')&&batchCalls[1].endsWith('offset=0')&&batchCalls[2].endsWith('offset=8388608'));
 assert(f.metrics.requests.filter(r=>r.operation==='chunk').every(r=>r.bytes<=8*1024*1024));
 assert.equal(f.metrics.identity.length,1);
 // A timeout may have committed only the first 4 MiB. A settled read must
 // precede any smaller replay; busy reconciliation is retried without resending.
 f=await fixture({transport:8*1024*1024,relayResume:true,chunkFailures:1,loseAck:true,partialAck:4*1024*1024,timeout:true,resumeBusy:2,fastRetry:true});
 f.el('file').files=[batched];await f.el('file').onchange();assert.equal(f.el('stage').textContent,'Uploaded',f.el('error').textContent);
 const rs=f.calls.filter(c=>c.endsWith('/resume'));assert.equal(rs.length,3);
 const sent=f.metrics.requests.filter(r=>r.operation==='chunk');assert(sent.slice(1).every(r=>r.bytes<=4*1024*1024));
 assert(f.calls.findIndex(c=>c.endsWith('/resume'))<f.calls.findIndex(c=>c.endsWith('offset=4194304')));
 f=await fixture({transport:8*1024*1024,relayResume:true,chunkFailures:1,loseAck:true,fastRetry:true});f.el('file').files=[batched];await f.el('file').onchange();
 assert.equal(f.el('stage').textContent,'Uploaded',f.el('error').textContent);assert.equal(f.calls.filter(c=>c.endsWith('offset=0')).length,1);
 // Virtual measured deadlines: a 325-second progressing request survives the
 // former 180-second absolute limit, while a stalled request is reconciled.
 f=await fixture({clock:true,progressive:'continue'});f.el('file').files=[file];let slowRun=f.el('file').onchange();
 while(!f.calls.some(c=>c.includes('/chunk')))await tick();await f.advance(330000);await slowRun;
 assert.equal(f.el('stage').textContent,'Uploaded',f.el('error').textContent);assert.equal(f.calls.filter(c=>c.includes('/chunk')).length,1);
 assert.equal(f.metrics.requests.find(r=>r.operation==='chunk').elapsed_ms,325000);assert.equal(f.deadlines[0],900000);
 f=await fixture({clock:true,progressive:'stall',transport:8*1024*1024,relayResume:true});f.el('file').files=[batched];slowRun=f.el('file').onchange();
 while(!f.calls.some(c=>c.includes('/chunk')))await tick();await f.advance(64000);await slowRun;
 assert.equal(f.el('stage').textContent,'Uploaded',f.el('error').textContent);assert(f.calls.some(c=>c.endsWith('/resume')));
 assert.equal(f.metrics.requests.find(r=>r.error==='timeout').elapsed_ms,61000);
 assert(f.metrics.requests.filter(r=>r.operation==='chunk'&&r.status===200).every(r=>r.bytes<=4*1024*1024));
 console.log('PASS: progressing 325s transfer, 60s idle deadline, settled fallback, 15min request cap');
 console.log('PASS: settled timeout offsets, bounded busy reconciliation and 4 MiB fallback');
 console.log('PASS: negotiated 8 MiB ordered batches, lost ACK and legacy fallback');
 console.log('PASS: controlled baseline 4 MiB interruption reproduced; same failure pattern completes after fix');
 console.log('PASS: retries, timeout recovery, permanent validation, retained identity and empty refresh;');
 console.log('PASS: fresh state; three modes; PSD only; clipboard fallback; removal; late upload ignored');
})().catch(e=>{console.error(e);process.exitCode=1});
