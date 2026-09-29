const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function shell(){
 const handlers={},timers=new Map();let seq=0,hidden=false,disconnected=false,fetches=0,reloads=0,observer;
 const storage=new Map(),button={disabled:true};
 const dialog={querySelector:()=>({textContent:'Connection error'})};
 const document={body:{},get hidden(){return hidden;},addEventListener:(k,f)=>handlers[k]=f,
  querySelectorAll:s=>s==='[role="dialog"]'?(disconnected?[dialog]:[]):[button]};
 const window={addEventListener:(k,f)=>handlers[k]=f,dispatchEvent(){}};
 const context={document,window,AbortController,URL,Event,Date,location:{href:'https://example.test/',reload(){reloads++;}},
  fetch:async()=>{fetches++;return {ok:true};},sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
  setTimeout:(f,delay)=>{timers.set(++seq,{f,delay});return seq;},clearTimeout:id=>timers.delete(id),
  MutationObserver:class{constructor(f){observer=f;}observe(){}disconnect(){}}};
 vm.runInNewContext(fs.readFileSync('components/session_recovery.js','utf8'),context);
 handlers.focus();handlers.pageshow();observer();assert.equal(fetches,0);assert.equal(timers.size,0);
 disconnected=true;observer();assert.equal(timers.size,1);
 hidden=true;handlers.visibilitychange();assert.equal(timers.size,0);
 hidden=false;handlers.visibilitychange();const pending=[...timers.values()][0];timers.clear();await pending.f();
 assert.equal(fetches,1);assert.equal(reloads,1);
 assert.equal(button.disabled,true); // Never fake recovery by unlocking Streamlit.
 disconnected=false;observer();assert.equal(timers.size,0);
 window.SportsCaveSessionRecovery.destroy();assert.equal(timers.size,0);
 console.log('Shell: healthy focus has zero I/O; hidden cancels; disconnected resume probes/reloads once; disabled state not bypassed.');
}
function checkpoint(){
 const events={},parentEvents={},docEvents={},timers=new Map(),storage=new Map(),sent=[];let seq=0;
 const parent={postMessage:m=>sent.push(m),dispatchEvent(){},addEventListener:(k,f)=>parentEvents[k]=f,removeEventListener:k=>delete parentEvents[k],
  document:{hidden:false,getElementById:()=>null,addEventListener:(k,f)=>docEvents[k]=f,removeEventListener:k=>delete docEvents[k]}};
 const context={parent,crypto:{randomUUID:()=>String(++seq)},Date,JSON,
  sessionStorage:{setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k),removeItem:k=>storage.delete(k)},
  addEventListener:(k,f)=>events[k]=f,setTimeout:(f,delay)=>{timers.set(++seq,{f,delay});return seq;},clearTimeout:k=>timers.delete(k)};
 vm.runInNewContext(fs.readFileSync('components/campaign_recovery/recovery.js','utf8'),context);
 const editor={id:'draft-1',version:2,name:'Draft',document:{content:{subject:'',preheader:''},copy_reviewed:false,middle_sections:[]}};
 events.message({source:parent,data:{type:'streamlit:render',args:{scope:'user',editor}}});
 const input=value=>docEvents.input({target:{closest:()=>true,getAttribute:()=> 'Subject',value}});
 input('A');input('AB');input('ABC');assert.equal(timers.size,1);assert.equal([...timers.values()][0].delay,750);
 assert.equal(sent.filter(m=>m.type==='streamlit:setComponentValue').length,0);
 parent.document.hidden=true;docEvents.visibilitychange();
 const send=sent.find(m=>m.type==='streamlit:setComponentValue');assert.equal(send.value.record.editor.document.content.subject,'ABC');
 assert.equal(storage.size,1);assert.equal(timers.size,0);
 const saved=JSON.parse(JSON.stringify(send.value.record.editor));saved.version++;
 events.message({source:parent,data:{type:'streamlit:render',args:{scope:'user',editor:saved,ack:send.value.event}}});
 assert.equal(storage.size,0);
 input('Keep on failure');parent.document.hidden=true;docEvents.visibilitychange();
 const failed=sent.filter(m=>m.type==='streamlit:setComponentValue').at(-1);
 events.message({source:parent,data:{type:'streamlit:render',args:{scope:'user',editor:failed.value.record.editor,ack:failed.value.event,failed:true,confirmed:false}}});
 assert.equal(storage.size,1); // Matching transient UI is not proof of a successful DB save.
 parentEvents['sc-campaign-discard']();assert.equal(storage.size,0);
 const sendsBeforeClose=sent.filter(m=>m.type==='streamlit:setComponentValue').length;
 events.pagehide();assert.equal(sent.filter(m=>m.type==='streamlit:setComponentValue').length,sendsBeforeClose);assert.equal(Object.keys(parentEvents).length,0);assert.equal(Object.keys(docEvents).length,0);
 console.log('Checkpoint: 750ms debounce; hide flush; durable pending copy; acknowledgement clears copy; unmount removes listeners.');
}
shell().then(checkpoint).catch(e=>{console.error(e);process.exitCode=1;});
