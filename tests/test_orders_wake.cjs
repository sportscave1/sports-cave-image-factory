'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../windows-upload-companion/orders-wake.js'),'utf8');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const cursor='b'.repeat(64);

function fixture({request,run=async()=>true,paired=true,stored=''}={}) {
  const state={staffQueueCredential:paired?'fixture-token':null,ordersNotificationCursor:stored};
  const timers=[],calls=[],writes=[];
  const scope=vm.createContext({AbortSignal,Date,Math,ordersTickRunning:false,
    osOrigin:'https://sports-cave-image-factory.onrender.com',ordersQueueTick:run,
    setTimeout:(resolve,ms)=>{timers.push({resolve,ms});},
    chrome:{storage:{local:{get:async()=>({...state}),set:async value=>{writes.push(value);Object.assign(state,value);}}}},
    fetch:async(url,options)=>{calls.push({url,options});return request?request(url,options):{ok:true,json:async()=>({enabled:true,version:cursor,changed:true})};},
  });
  vm.runInContext(source,scope);
  const start=()=>vm.runInContext('ensureOrdersNotifications()',scope);
  const advance=async()=>{assert.ok(timers.length);timers.shift().resolve();await flush();};
  const stop=async promise=>{state.staffQueueCredential=null;while(timers.length)timers.shift().resolve();await flush();await promise;};
  return {scope,state,timers,calls,writes,start,advance,stop};
}

test('unpaired notification channel makes no request',async()=>{
  const f=fixture({paired:false});await f.start();assert.equal(f.calls.length,0);
});

test('committed hint wakes guarded tick and persists cursor only after handling',async()=>{
  let finish;const f=fixture({run:()=>new Promise(resolve=>{finish=resolve;})});
  const pending=f.start();await flush();
  assert.equal(f.writes.length,0);
  assert.equal(f.calls[0].options.credentials,'omit');
  assert.equal(f.calls[0].options.headers.Authorization,'Bearer fixture-token');
  assert.equal(f.calls[0].url,'https://sports-cave-image-factory.onrender.com/api/orders-companion/notifications?after=');
  finish(true);await flush();assert.equal(f.state.ordersNotificationCursor,cursor);
  await f.stop(pending);
});

test('failed tick leaves cursor replayable and backs off without changing queue permits',async()=>{
  const f=fixture({run:async()=>false,stored:'a'.repeat(64)});
  const pending=f.start();await flush();
  assert.equal(f.state.ordersNotificationCursor,'a'.repeat(64));
  assert.equal(f.writes.length,0);assert.ok(f.timers[0].ms>=2000);
  await f.stop(pending);
});

test('reconnected worker sends saved cursor and idle reply never starts native work',async()=>{
  const f=fixture({stored:cursor,run:()=>assert.fail('No native work on timeout'),request:async()=>({ok:true,json:async()=>({enabled:true,version:cursor,changed:false})})});
  const pending=f.start();await flush();
  assert.ok(f.calls[0].url.endsWith('after='+cursor));assert.equal(f.writes.length,0);
  await f.stop(pending);
});

test('notification loop is single and defers while another native stage runs',async()=>{
  const f=fixture();f.scope.ordersTickRunning=true;
  const pending=f.start();await flush();await f.start();
  assert.equal(f.calls.length,0);assert.equal(f.timers[0].ms,1000);
  f.scope.ordersTickRunning=false;await f.advance();assert.equal(f.calls.length,1);
  await f.stop(pending);
});

test('authentication errors and malformed hints back off without ticking or acknowledging',async()=>{
  for(const response of [{ok:false},{ok:true,json:async()=>({enabled:true,version:'https://fixture.invalid',changed:true})}]) {
    const f=fixture({request:async()=>response,run:()=>assert.fail('Invalid hint')});
    const pending=f.start();await flush();assert.equal(f.writes.length,0);assert.ok(f.timers[0].ms>=2000);
    await f.stop(pending);
  }
});

test('pair rotation during a native stage does not acknowledge the old credential',async()=>{
  const f=fixture({run:async()=>{f.state.staffQueueCredential=null;return true;}});
  await f.start();assert.equal(f.writes.length,0);
});

test('disabled server does not run actions and waits before reconnecting',async()=>{
  const f=fixture({request:async()=>({ok:true,json:async()=>({enabled:false,changed:false})}),run:()=>assert.fail('Disabled')});
  const pending=f.start();await flush();assert.equal(f.writes.length,0);assert.equal(f.timers[0].ms,30000);
  await f.stop(pending);
});
