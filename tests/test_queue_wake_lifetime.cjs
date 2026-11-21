const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync('windows-upload-companion/queue-wake.js','utf8');

test('queue wake tolerates missing, reloaded, and synchronously invalidated extension contexts',async()=>{
  for(const chrome of [undefined,{}, {runtime:{}}, {runtime:{id:'test',sendMessage(){throw Error('Extension context invalidated');}}},
    {runtime:{id:'test',sendMessage:()=>Promise.reject(Error('Worker restarting'))}}]) {
    const listeners={},timers=[];
    vm.runInNewContext(source,{chrome,document:{addEventListener:(name,fn)=>listeners[name]=fn},setTimeout:fn=>timers.push(fn)});
    assert.doesNotThrow(()=>listeners.click({isTrusted:true,target:{closest:()=>({textContent:'Add to queue'})}}));
    for(const fn of timers)assert.doesNotThrow(fn);
    assert.doesNotThrow(()=>listeners['sc-design-edit-queued']());
    await Promise.resolve();
  }
});

test('a live extension is woken after committed queue actions and ignores unrelated clicks',()=>{
  const listeners={},timers=[],sent=[];
  vm.runInNewContext(source,{chrome:{runtime:{id:'test',sendMessage:m=>{sent.push(m);return Promise.resolve();}}},
    document:{addEventListener:(name,fn)=>listeners[name]=fn},setTimeout:fn=>timers.push(fn)});
  listeners.click({isTrusted:false});
  listeners.click({isTrusted:true,target:{closest:()=>({textContent:'Other action'})}});
  assert.equal(timers.length,0);
  listeners.click({isTrusted:true,target:{closest:()=>({textContent:'Add to queue'})}});
  timers.forEach(fn=>fn());listeners['sc-design-edit-queued']();
  assert.equal(sent.length,3);
  assert.ok(sent.every(m=>m.type==='os:wake-designs'));
});
