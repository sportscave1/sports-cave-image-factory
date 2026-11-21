'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname,'../windows-upload-companion/orders-queue.js'),'utf8');

function context(token, request) {
  const writes=[];
  const chrome={
    storage:{local:{get:async()=>({staffQueueCredential:token}),set:async value=>writes.push(value)}},
    alarms:{get:async()=>null,create:async()=>{},onAlarm:{addListener() {}}},
    runtime:{onStartup:{addListener() {}},onInstalled:{addListener() {}}},
  };
  const scope=vm.createContext({chrome,fetch:request,AbortSignal,Date,setInterval,clearInterval,
    osOrigin:'https://sports-cave-image-factory.onrender.com'});
  vm.runInContext(source,scope);
  return {scope,writes};
}

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
