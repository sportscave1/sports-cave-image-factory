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
context.update({compact:2,devices:[{id:'pc',seq:9,connected:true,state_delta:{base_seq:8,changes:{mode:'running'},tasks:{remove:['saved'],upsert:[{id:'other',name:'Only new task'}]}}}]});
assert.equal(context.state.mode,'running');assert.equal(context.state.tasks.length,1);assert.equal(context.state.tasks[0].id,'other');
context.update({compact:2,devices:[{id:'pc',seq:10,state_delta:{base_seq:7,changes:{},tasks:{remove:[],upsert:[]}}}]});
assert.equal(context.after,'');assert.equal(context.device.seq,9);
context.active=()=>false;
context.update({compact:2,devices:[{id:'pc',seq:9,connected:false},{id:'new-pc',seq:1,connected:true}]});
assert.equal(context.device.id,'new-pc');assert.equal(context.after,'');assert.equal(context.state.tasks,undefined);assert.equal(context.selected,'');
context.update({compact:2,devices:[{id:'new-pc',seq:1,connected:true,state:{mode:'idle',tasks:[{id:'new-task',name:'New PC task'}]}}]});
assert.equal(context.state.tasks[0].id,'new-task');
context.update({devices:[]});assert.equal(context.device,null);assert.equal(context.selected,'');
console.log('PASS compact metadata merge, fresh task changes, stale response rejection, revocation clears selection');

const poll=source.slice(source.indexOf('async function poll(){'),source.indexOf("$('record').onclick"));
(async()=>{
 let calls=0,resolve;
 const c={compactLevel:1,pollRunning:false,pollAbort:null,stopped:false,device:{id:'pc'},after:'7',document:{hidden:false},AbortController,
  api:()=>{calls++;return new Promise(r=>resolve=r);},update:()=>{c.stopped=true;},reconcile(){},
  $:()=>({textContent:''}),error(){},render(){},pollDelay:async()=>{c.stopped=true;}};
 vm.createContext(c);vm.runInContext(poll,c);
 const first=c.poll();await c.poll();assert.equal(calls,1);resolve({devices:[]});await first;assert.equal(c.pollRunning,false);
 c.stopped=false;c.document.hidden=true;await c.poll();assert.equal(calls,1);
 c.stopped=false;c.document.hidden=false;let delay;
 c.api=async()=>{throw Error('offline');};c.pollDelay=async ms=>{delay=ms;c.stopped=true;};
 await c.poll();assert.equal(c.transportOK,false);assert(delay>=1600&&delay<=2400);
 console.log('PASS single poll loop, hidden page suspends requests, bounded reconnect delay');
 const send=source.slice(source.indexOf('async function send(kind,'),source.indexOf('async function reconcile()'));
 let blocked='';const guard={device:{id:'new-pc',connected:true},error:text=>blocked=text};
 vm.createContext(guard);vm.runInContext(send,guard);
 assert.equal(await guard.send('play',{id:'old-pc-task'}),null);assert(blocked.startsWith('Loading'));
 console.log('PASS metadata-only PC switch blocks controls until its own snapshot arrives');
})().catch(e=>{console.error(e);process.exitCode=1;});
