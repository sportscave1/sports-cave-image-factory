const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const script=fs.readFileSync('components/product_uploads/focus_generation.js','utf8');
function fixture(){
 const stored=new Map(), listeners=new Map(), timers=new Map(), calls=[];
 let next=0, mounted=false, height=600, complete=false, pagehide;
 const main={scrollTop:0,getBoundingClientRect:()=>({top:0}),scrollTo:args=>calls.push(args)};
 const gallery={getBoundingClientRect:()=>({height:140}),contentDocument:{querySelectorAll:()=>[{complete,naturalWidth:complete?100:0}]}};
 const target={closest:()=>main,querySelector:()=>gallery,getBoundingClientRect:()=>({top:350,width:1000,height})};
 const host={location:{href:'http://local/?page=product_uploads'},sessionStorage:{getItem:k=>stored.get(k),setItem:(k,v)=>stored.set(k,v)},document:{querySelector:()=>mounted?target:null,getElementById:()=>({getBoundingClientRect:()=>({bottom:64})})},addEventListener:(t,f)=>listeners.set(t,f),removeEventListener:t=>listeners.delete(t)};
 const run=token=>vm.runInNewContext(script,{focusToken:token,window:{parent:host},setTimeout:f=>{timers.set(++next,f);return next;},clearTimeout:id=>timers.delete(id),addEventListener:(t,f)=>{pagehide=f},removeEventListener:()=>{pagehide=null}});
 const tick=()=>{const pending=[...timers.values()];timers.clear();pending.forEach(f=>f());};
 return {run,tick,calls,host,listeners,timers,mount:()=>{mounted=true},ready:()=>{complete=true},resize:()=>{height+=50},unmount:()=>pagehide()};
}
test('waits for mounted decoded previews and stable layout; scrolls only content below header once',()=>{
 const f=fixture();f.run('one');f.tick();assert.equal(f.calls.length,0);
 f.mount();f.tick();assert.equal(f.calls.length,0);f.ready();f.tick();f.resize();f.tick();f.tick();assert.equal(f.calls.length,0);
 f.tick();assert.equal(f.calls.length,1);assert.equal(f.calls[0].top,274);
 assert.equal(f.timers.size,0);assert.equal(f.listeners.size,0);
 f.run('one');assert.equal(f.calls.length,1);
 f.run('two');f.tick();f.tick();assert.equal(f.calls.length,2);
});
for(const event of ['wheel','pointerdown','touchstart','keydown','popstate'])test(event+' cancels pending scroll without a later jump',()=>{
 const f=fixture();f.run('one');f.listeners.get(event)();f.mount();f.ready();f.tick();f.run('one');f.tick();assert.equal(f.calls.length,0);assert.equal(f.listeners.size,0);
});
test('unmount, route change and failed mount release timers and listeners',()=>{
 for(const mode of ['unmount','route','timeout']){
  const f=fixture();f.run(mode);
  if(mode==='unmount')f.unmount();
  if(mode==='route')f.host.location.href='http://local/?page=files';
  for(let n=0;n<55;n++)f.tick();
  assert.equal(f.calls.length,0);assert.equal(f.timers.size,0);assert.equal(f.listeners.size,0);
 }
});
test('helper is emitted after completed outputs, never during generation polling',()=>{
 const source=fs.readFileSync('product_upload_mockups_ui.py','utf8');
 assert.ok(source.indexOf('render_outputs(app,result,row,user,name)')<source.indexOf('focus_generation(st.session_state'));
 assert.ok(!source.includes('if pending or result:'));
});
