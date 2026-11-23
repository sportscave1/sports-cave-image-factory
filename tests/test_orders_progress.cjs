const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../windows-upload-companion/orders-progress.js'),'utf8');
const flush=()=>new Promise(setImmediate);
test('progress coalesces while busy, publishes only bounded fields and stops with its handoff',async()=>{
 const calls=[];let finish;
 const scope=vm.createContext({Date,AbortSignal,osOrigin:'https://sports-cave-image-factory.onrender.com',
  chrome:{runtime:{getManifest:()=>({version:'1.7.40'})},storage:{local:{get:async()=>({staffQueueCredential:'fixture'})}}},
  fetch:async(url,options)=>{calls.push({url,options});await new Promise(r=>finish=r);return{ok:true}}});
 vm.runInContext(source,scope);scope.plan={key:'prodigi_prepare:1',token:'a'.repeat(43)};
 vm.runInContext('ordersProgressBegin(plan)',scope);await flush();
 vm.runInContext("ordersProgressStage('editor');ordersProgressStage('transfer')",scope);assert.equal(calls.length,1);
 finish();await flush();assert.equal(calls.length,2);
 const data=JSON.parse(calls[1].options.body);assert.equal(data.stage,'transfer');assert.equal(data.sequence,2);assert.equal(data.version,'1.7.40');
 assert.deepEqual(Object.keys(data).sort(),['attempt','elapsed_ms','key','kind','retry_in_ms','sequence','stage','token','version']);
 vm.runInContext('ordersProgressEnd()',scope);finish();await flush();vm.runInContext("ordersProgressStage('save')",scope);assert.equal(calls.length,2);
});
