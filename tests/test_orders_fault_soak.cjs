const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../windows-upload-companion/orders-queue.js'),'utf8');
test('1000 wake bursts with duplicates and intermittent transport failure serialize native work',async()=>{
 const state={staffQueueCredential:'fixture'},native=new Set();let job=null,active=0,peak=0,failed=false,calls=0;
 const chrome={storage:{local:{get:async()=>state,set:async v=>Object.assign(state,v),remove:async k=>delete state[k]}},
   alarms:{get:async()=>({}),create:async()=>{},onAlarm:{addListener(){}}},runtime:{onStartup:{addListener(){}},onInstalled:{addListener(){}}}};
 const scope=vm.createContext({chrome,Date,AbortSignal,setInterval,clearInterval,osOrigin:'https://sports-cave-image-factory.onrender.com',
  fetch:async()=>{calls++;if(failed){failed=false;throw Error('Synthetic disconnect before claim');}const browser=job;job=null;return{ok:true,json:async()=>({enabled:true,browser})}},
  prodigiBrowserRun:async plan=>{peak=Math.max(peak,++active);assert(!native.has(plan.key));native.add(plan.key);await new Promise(setImmediate);active--;return{status:'Waiting for order'}}});
 vm.runInContext(source,scope);
 for(let i=0;i<1000;i++){
   job={key:'fixture-'+i,order_id:'order-'+i};failed=i%17===0;
   await Promise.all([vm.runInContext('ordersQueueTick()',scope),vm.runInContext('ordersQueueTick()',scope),vm.runInContext('ordersQueueTick()',scope)]);
   if(job)await vm.runInContext('ordersQueueTick()',scope);
 }
 assert.equal(native.size,1000);assert.equal(peak,1);assert.equal(active,0);assert.equal(calls,2059);
});
