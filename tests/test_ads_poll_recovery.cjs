const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('windows-upload-companion/ad-queue.js','utf8');
function harness(statuses){
 const calls=[],delays=[];
 const c=vm.createContext({osOrigin:'https://fixture.invalid',AbortSignal,Math,
  delay:async ms=>delays.push(ms),fetch:async(url,options)=>{
   calls.push({url,options});const status=statuses.shift();if(status instanceof Error)throw status;
   return {status,ok:status===200};},
  chrome:{alarms:{onAlarm:{addListener(){}}},runtime:{onStartup:{addListener(){}},onInstalled:{addListener(){}}}}});
 vm.runInContext(source,c);return {c,calls,delays};
}
test('temporary server overload retries the identical checkpoint after a bounded delay',async()=>{
 const h=harness([503,503,200]);
 const result=await vm.runInContext("pollAdCheckpoint('fixture',{id:'same',state:'submitted'})",h.c);
 assert.equal(result.status,200);assert.equal(h.calls.length,3);
 assert.deepEqual([...new Set(h.calls.map(v=>v.options.body))],['{"id":"same","state":"submitted"}']);
 assert.ok(h.delays[0]>=2000 && h.delays[0]<2500);
 assert.ok(h.delays[1]>=4000 && h.delays[1]<4500);
});
test('persistent overload releases this poll after three attempts',async()=>{
 const h=harness([503,503,503,200]);
 assert.equal((await vm.runInContext("pollAdCheckpoint('fixture',{})",h.c)).status,503);
 assert.equal(h.calls.length,3);
});
for(const status of [200,403,409])test(`status ${status} is returned without replay`,async()=>{
 const h=harness([status,200]);
 assert.equal((await vm.runInContext("pollAdCheckpoint('fixture',{})",h.c)).status,status);
 assert.equal(h.calls.length,1);assert.equal(h.delays.length,0);
});
test('an unknown network outcome waits for durable reconciliation on the next alarm',async()=>{
 const h=harness([new Error('connection lost'),200]);
 await assert.rejects(vm.runInContext("pollAdCheckpoint('fixture',{})",h.c),/connection lost/);
 assert.equal(h.calls.length,1);
});

test('a long transfer reports contact without starting a concurrent claim or send',async()=>{
 const h=harness([200,200]);
 h.c.staffRead=async()=> 'fixture';h.c.staffDeviceKey='paired';
 await vm.runInContext('adTickRunning=true;adQueueTick()',h.c);
 assert.equal(h.calls.length,1);
 assert.deepEqual(JSON.parse(h.calls[0].options.body),{heartbeat_only:true});
 assert.equal(await vm.runInContext('adTickRunning',h.c),true);
 assert.equal(await vm.runInContext('adHeartbeatRunning',h.c),false);
 await vm.runInContext('adQueueTick()',h.c);
 assert.equal(h.calls.length,2);
});

test('a lost contact response frees the heartbeat for the next durable alarm',async()=>{
 const h=harness([new Error('offline'),200]);
 h.c.staffRead=async()=> 'fixture';h.c.staffDeviceKey='paired';
 await vm.runInContext('adTickRunning=true;adQueueTick();',h.c);
 await vm.runInContext('adQueueTick()',h.c);
 assert.equal(h.calls.length,2);
 assert.equal(await vm.runInContext('adHeartbeatRunning',h.c),false);
});
