'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname,'../windows-upload-companion/orders-queue.js'),'utf8');

function context(token, request) {
  const writes=[],alarms=[];
  const chrome={
    storage:{local:{get:async()=>({staffQueueCredential:token}),set:async value=>writes.push(value)}},
    alarms:{get:async()=>null,create:async (...args)=>alarms.push(args),onAlarm:{addListener() {}}},
    runtime:{onStartup:{addListener() {}},onInstalled:{addListener() {}}},
  };
  const scope=vm.createContext({chrome,fetch:request,AbortSignal,Date,setInterval,clearInterval,
    osOrigin:'https://sports-cave-image-factory.onrender.com'});
  vm.runInContext(source,scope);
  return {scope,writes,alarms};
}

test('reload restores a paired alarm without requiring a browser startup event',async()=>{
  const {alarms}=context('fixture',()=>assert.fail('Alarm setup must not send artwork'));
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(alarms.length,1);
  assert.equal(alarms[0][0],'sports-cave-orders-queue');
  assert.equal(alarms[0][1].periodInMinutes,0.5);
});

test('unpaired extension never contacts a service',async()=>{
  const {scope}=context(null,()=>assert.fail('No HTTP expected'));
  await vm.runInContext('ordersQueueTick()',scope);
});

test('paired worker calls only OS with no cookies or supplier credentials',async()=>{
  const calls=[];
  const {scope,writes}=context('fixture-device-token',async (url,options)=>{
    calls.push({url,options});
    return {ok:true,json:async()=>({enabled:true,job:{allocation_id:1,status:'Needs QA'}})};
  });
  await vm.runInContext('ordersQueueTick()',scope);
  assert.equal(calls.length,1);
  assert.equal(calls[0].url,'https://sports-cave-image-factory.onrender.com/api/orders-companion/tick');
  assert.equal(calls[0].options.credentials,'omit');
  assert.equal(calls[0].options.body,'{}');
  assert.equal(writes[0].ordersCompanionLast.job.status,'Needs QA');
});

test('overlapping alarms do not create overlapping requests',async()=>{
  let finish,calls=0;
  const {scope}=context('fixture',()=>{calls++;return new Promise(resolve=>{finish=resolve;});});
  const first=vm.runInContext('ordersQueueTick()',scope);
  await new Promise(resolve=>setImmediate(resolve));
  await vm.runInContext('ordersQueueTick()',scope);
  assert.equal(calls,1);
  finish({ok:false});
  await first;
});


test('successful stages continue immediately, stop on review, and never overlap',async()=>{
  const calls=[],stages=['Awaiting browser upload','Awaiting dashboard QA','Waiting for order','Needs review'];
  const {scope}=context('fixture',async(url,options)=>{
    calls.push(options);return {ok:true,json:async()=>({enabled:true,browser:{key:'pinned'},job:{allocation_id:1}})};
  });
  scope.prodigiBrowserRun=async()=>({status:stages.shift()});
  await vm.runInContext('ordersQueueTick()',scope);
  assert.equal(calls.length,4);
  assert.equal(calls[0].headers['X-Sports-Cave-Orders-Sequential'],'1');
});

test('a continuously successful queue yields after six stages',async()=>{
  let calls=0;
  const {scope}=context('fixture',async()=>{calls++;return {ok:true,json:async()=>({enabled:true,browser:{key:'pinned'},job:{allocation_id:1}})}});
  scope.prodigiBrowserRun=async()=>({status:'Waiting for order'});
  await vm.runInContext('ordersQueueTick()',scope);
  assert.equal(calls,6);
});
