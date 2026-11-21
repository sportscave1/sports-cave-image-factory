const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {execFileSync}=require('node:child_process');
const reference=execFileSync('git',['merge-base','HEAD','origin/main'],{encoding:'utf8'}).trim();
const baseline=execFileSync('git',['show',reference+':windows-upload-companion/composer.js'],{encoding:'utf8'});
const candidate=fs.readFileSync('windows-upload-companion/composer.js','utf8');
function probe(source,design=false,ad=false){
  const state={text:'',generating:false,alert:'',visible:true,reads:0};
  const body={matches:()=>false,get innerText(){state.reads++;return state.text;}};
  const alert={get innerText(){return state.alert;},getClientRects:()=>state.visible?[{}]:[]};
  const context={design,ad,location:{href:'https://chatgpt.com/c/synthetic'},
    document:{querySelector:()=>state.generating?{}:null,
      querySelectorAll:q=>q==='[role="alert"]'?(state.alert?[alert]:[]):[body]}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function projectProgress()'),source.indexOf('  function watchDesignResponse()')),context);
  return {state,context,read:()=>JSON.parse(JSON.stringify(context.projectProgress()))};
}
test('cached analysis matches original through streaming, alerts, navigation and changed output',()=>{
  for(const [design,ad] of [[false,false],[true,false],[false,true]]){
    const before=probe(baseline,design,ad),after=probe(candidate,design,ad);
    const cases=[{text:'Working'}, {text:'Working'}, {generating:true}, {text:'SC_DESIGN_BLOCKED: Missing PSD'},
      {generating:false}, {alert:'Something went wrong'}, {visible:false}, {visible:true,alert:'Network error'},
      {alert:'',text:'The generation was rejected. The replacement PSD is still pending.'},
      {text:'The replacement PSD was delivered.'}, {text:'SC_UPLOAD_BLOCKED: SHOPIFY'},
      {text:'SC_AD_BLOCKED: Missing files'}, {text:'x'.repeat(1024*1024+1)}, {text:''}];
    for(const change of cases){Object.assign(before.state,change);Object.assign(after.state,change);assert.deepEqual(after.read(),before.read());}
    before.context.location.href=after.context.location.href='https://chatgpt.com/c/another-synthetic';
    assert.deepEqual(after.read(),before.read());
    assert.equal(after.state.reads,before.state.reads,'every read still inspects current DOM');
  }
});
test('memo is bounded and returned objects cannot corrupt later observations',()=>{
  const f=probe(candidate,true);f.state.text='SC_DESIGN_BLOCKED: Missing original';f.read();
  const result=f.context.projectProgress();result.reason='caller mutation';
  assert.match(f.read().reason,/Missing original/);
  f.state.text='x'.repeat(1024*1024+1);f.read();assert.equal(f.context.projectProgress.memo,null);
});

function watcher(design){
  const state={text:'Working',generating:false};let serial=0;
  const intervals=new Map(),timeouts=new Map(),listeners=new Set(),messages=[];
  const body={matches:()=>false,get innerText(){return state.text;}};
  const context={design,ad:false,conversation:/\/c\//,location:{href:'https://chatgpt.com/c/synthetic'},
    document:{querySelector:()=>state.generating?{}:null,querySelectorAll:q=>q==='[role="alert"]'?[]:[body]},
    chrome:{runtime:{id:'synthetic',sendMessage:async message=>{messages.push(message);return {accepted:true};}}},
    setInterval:(fn,ms)=>{const id=++serial;intervals.set(id,{fn,ms});return id;},clearInterval:id=>intervals.delete(id),
    setTimeout:(fn,ms)=>{const id=++serial;timeouts.set(id,{fn,ms});return id;},clearTimeout:id=>timeouts.delete(id),
    addEventListener:(_event,fn)=>listeners.add(fn),removeEventListener:(_event,fn)=>listeners.delete(fn)};
  vm.createContext(context);
  vm.runInContext(candidate.slice(candidate.indexOf('  function projectProgress()'),candidate.indexOf('  chrome.runtime.onMessage.addListener')),context);
  return {state,context,intervals,timeouts,listeners,messages};
}
test('design monitoring stays single, requires two observations and removes its timers on handoff',async()=>{
  const f=watcher(true);f.context.watchDesignResponse();f.context.watchDesignResponse();
  assert.equal(f.intervals.size,1);assert.equal(f.timeouts.size,1);assert.equal(f.listeners.size,1);
  assert.equal([...f.intervals.values()][0].ms,1500);
  f.context.document.hidden=true;
  f.state.text='SC_DESIGN_BLOCKED: Missing PSD';const tick=[...f.intervals.values()][0].fn;
  tick();assert.equal(f.messages.length,0);tick();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(f.messages.length,1);assert.equal(f.intervals.size,0);assert.equal(f.timeouts.size,0);assert.equal(f.listeners.size,0);
});
test('real navigation tears down while bfcache and background monitoring remain intact',()=>{
  const f=watcher(true);f.context.watchDesignResponse();const leave=[...f.listeners][0];
  leave({persisted:true});assert.equal(f.intervals.size,1);
  f.context.projectProgress();leave({persisted:false});
  assert.equal(f.intervals.size,0);assert.equal(f.timeouts.size,0);assert.equal(f.listeners.size,0);assert.equal(f.context.projectProgress.memo,null);
  f.context.watchDesignResponse();[...f.timeouts.values()][0].fn();
  assert.equal(f.intervals.size,0);assert.equal(f.timeouts.size,0);assert.equal(f.listeners.size,0);
});
test('upload monitoring remains one bounded watcher and reports the unchanged blocker once',async()=>{
  const f=watcher(false);f.context.watchStaffResponse();f.context.watchStaffResponse();
  assert.equal(f.intervals.size,1);assert.equal([...f.intervals.values()][0].ms,3500);
  f.state.text='SC_UPLOAD_BLOCKED: SHOPIFY';[...f.intervals.values()][0].fn();await Promise.resolve();
  assert.deepEqual(JSON.parse(JSON.stringify(f.messages)),[{type:'project:blocked',code:'SHOPIFY'}]);
  assert.equal(f.intervals.size,0);assert.equal(f.timeouts.size,0);assert.equal(f.listeners.size,0);
});
