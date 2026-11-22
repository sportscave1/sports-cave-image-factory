const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../windows-upload-companion/prodigi-wait.js'),'utf8');
function setup(){
 const timers=new Map();let next=0,callback,disconnected=0;
 const context=vm.createContext({queueMicrotask,document:{documentElement:{}},setTimeout:(fn,ms)=>{const id=++next;timers.set(id,{fn,ms});return id},clearTimeout:id=>timers.delete(id),
   MutationObserver:class{constructor(fn){callback=fn}observe(){}disconnect(){disconnected++}}});
 vm.runInContext(source,context);return{context,timers,mutate:()=>callback(),disconnected:()=>disconnected};
}
test('ready evidence has zero timers and no observer',async()=>{
 const h=setup();h.context.check=()=> 'ready';assert.equal(await vm.runInContext('prodigiObserveReady(check)',h.context),'ready');assert.equal(h.timers.size,0);
});
test('DOM changes wake immediately and clean all resources',async()=>{
 const h=setup();let ready=false;h.context.check=()=>ready?'exact item':null;
 const result=vm.runInContext('prodigiObserveReady(check)',h.context);ready=true;h.mutate();h.mutate();
 assert.equal(await result,'exact item');assert.equal(h.timers.size,0);assert.equal(h.disconnected(),1);
});
test('property-only updates use fallback and missing evidence has a bounded deadline',async()=>{
 const h=setup();let ready=false;h.context.check=()=>ready?'ready':null;
 const result=vm.runInContext('prodigiObserveReady(check)',h.context);ready=true;
 [...h.timers.values()].find(t=>t.ms===1000).fn();assert.equal(await result,'ready');assert.equal(h.timers.size,0);
 const x=setup();x.context.check=()=>null;const timed=vm.runInContext('prodigiObserveReady(check)',x.context);
 [...x.timers.values()].find(t=>t.ms===120000).fn();await assert.rejects(timed,/did not finish loading/);assert.equal(x.disconnected(),1);assert.equal(x.timers.size,0);
});
test('identity errors are surfaced and still release observers',async()=>{
 const h=setup();let calls=0;h.context.check=()=>{if(++calls>2)throw Error('Wrong item');return null};
 const result=vm.runInContext('prodigiObserveReady(check)',h.context);h.mutate();await assert.rejects(result,/Wrong item/);assert.equal(h.timers.size,0);
});
