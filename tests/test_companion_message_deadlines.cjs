const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const helper=fs.readFileSync('windows-upload-companion/message-deadline.js','utf8');
const worker=fs.readFileSync('windows-upload-companion/worker.js','utf8');
const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
test('repair Send gets the full composer readiness window',async()=>{
 const delays=[];
 const c=vm.createContext({chrome:{tabs:{sendMessage:async()=>({found:true})}},
 setTimeout:(f,ms)=>{delays.push(ms);return 1;},clearTimeout(){}});
 vm.runInContext(helper,c);
 await vm.runInContext("companionMessage(1,{type:'project:ad-repair-send'},{frameId:0})",c);
 assert.deepEqual(delays,[180000]);
});
test('hung progress expires, clears its timer and permits the next read',async()=>{
 const timers=new Map();let id=0,resolve,hang=true;
 const c=vm.createContext({chrome:{tabs:{sendMessage:()=>hang?new Promise(r=>resolve=r):Promise.resolve({ok:true})}},
 setTimeout:(f,ms)=>{timers.set(++id,{f,ms});return id;},clearTimeout:i=>timers.delete(i)});
 vm.runInContext(helper,c);
 const request=vm.runInContext("companionMessage(1,{type:'project:progress'},{frameId:0})",c);
 const rejected=assert.rejects(request,/timed out/);await flush();
 assert.equal([...timers.values()][0].ms,8000);[...timers.values()][0].f();await rejected;
 assert.equal(timers.size,0);resolve({late:true});await flush();hang=false;
 assert.equal((await vm.runInContext("companionMessage(1,{type:'project:progress'},{frameId:0})",c)).ok,true);
 assert.equal(timers.size,0);
});
test('hung send remains uncertain after permit and frees queue without permitting a late send',async()=>{
 const timers=new Map(),records={};let id=0;
 const c=vm.createContext({importScripts(){},setTimeout:(f,ms)=>{timers.set(++id,{f,ms});return id;},clearTimeout:i=>timers.delete(i),
 setInterval:()=>123,clearInterval(){},chrome:{runtime:{onMessage:{addListener(){}}},
 storage:{local:{set:async value=>Object.assign(records,value),get:async()=>({})}},tabs:{
 create:async()=>({id:7}),sendMessage:async(tab,msg)=>msg.type==='project:ready'?{ready:true}:new Promise(()=>{})}}});
 vm.runInContext(helper+'\n'+worker+"\nglobalThis.operation={sending:true};pending.set('fixture',operation);globalThis.finished=run('fixture','prompt',operation);",c);
 await flush();assert.equal([...timers.values()][0].ms,180000);
 [...timers.values()][0].f();await c.finished;
 assert.equal(records['upload:fixture'].state,'uncertain');assert.equal(timers.size,0);
 assert.equal(await vm.runInContext("pending.size",c),0);
 const permit=await vm.runInContext("permit({id:'fixture'},{frameId:0,tab:{id:7},url:project})",c);
 assert.equal(permit.ok,false);
});

test('ad transfer fast followup is bounded and only follows verified progress',()=>{
 const timers=[];
 const c=vm.createContext({setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},
 chrome:{alarms:{onAlarm:{addListener(){}}},runtime:{onStartup:{addListener(){}},onInstalled:{addListener(){}}}}});
 vm.runInContext(fs.readFileSync('windows-upload-companion/ad-queue.js','utf8'),c);
 vm.runInContext("followUpAdTransfer(undefined);followUpAdTransfer('failed');",c);assert.equal(timers.length,0);
 vm.runInContext("followUpAdTransfer('received');followUpAdTransfer('received');",c);
 assert.equal(timers.length,1);assert.equal(timers[0].ms,250);
});
