const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('task_recorder/panel.js','utf8');
const update=source.slice(source.indexOf('function update(result){'),source.indexOf('\nasync function confirmCommand'));
const previous={id:'pc',seq:7,state:{mode:'running',tasks:[{id:'saved',name:'Keep'}]},connected:true};
let renders=0;
const context={devices:[previous],device:previous,state:previous.state,selected:'saved',lastSeq:7,after:'7',transportOK:true,
 active:()=>true,renames:new Map(),details:null,values:{},tasks:()=>context.state.tasks||[],sessionStorage:{setItem(){}},render:()=>renders++};
vm.createContext(context);vm.runInContext(update,context);
context.update({devices:[{id:'pc',seq:7,connected:false,last_seen:123}]});
assert.equal(context.state.tasks[0].name,'Keep');assert.equal(context.device.connected,false);
context.update({devices:[{id:'pc',seq:8,connected:true,state:{mode:'completed',tasks:[{id:'saved',name:'Updated'}]}}]});
context.update({devices:[{id:'pc',seq:7,connected:true}]});
assert.equal(context.state.mode,'completed');assert.equal(context.state.tasks[0].name,'Updated');assert.equal(renders,2);
context.update({devices:[]});assert.equal(context.device,null);assert.equal(context.selected,'');
console.log('PASS compact metadata merge, fresh task changes, stale response rejection, revocation clears selection');

const poll=source.slice(source.indexOf('async function poll(){'),source.indexOf("$('record').onclick"));
(async()=>{
 let calls=0,resolve;
 const c={pollRunning:false,pollAbort:null,stopped:false,device:{id:'pc'},after:'7',document:{hidden:false},AbortController,
  api:()=>{calls++;return new Promise(r=>resolve=r);},update:()=>{c.stopped=true;},reconcile(){},
  $:()=>({textContent:''}),error(){},render(){},pollDelay:async()=>{c.stopped=true;}};
 vm.createContext(c);vm.runInContext(poll,c);
 const first=c.poll();await c.poll();assert.equal(calls,1);resolve({devices:[]});await first;assert.equal(c.pollRunning,false);
 c.stopped=false;c.document.hidden=true;await c.poll();assert.equal(calls,1);
 c.stopped=false;c.document.hidden=false;let delay;
 c.api=async()=>{throw Error('offline');};c.pollDelay=async ms=>{delay=ms;c.stopped=true;};
 await c.poll();assert.equal(c.transportOK,false);assert.equal(delay,2000);
 console.log('PASS single poll loop, hidden page suspends requests, bounded reconnect delay');
})().catch(e=>{console.error(e);process.exitCode=1;});
