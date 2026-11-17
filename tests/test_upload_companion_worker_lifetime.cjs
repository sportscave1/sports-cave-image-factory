const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(process.env.SC_WORKER_TEST_SOURCE || path.join(__dirname,
  '../windows-upload-companion/worker.js'), 'utf8');

test('Slow handoff stays active beyond MV3 idle timeout and releases its timer on every outcome', async () => {
  for (const outcome of ['submitted','failed','uncertain','cancelled','throw']) {
    let now=0, lastActivity=0, nextId=0;
    const timers=new Map(), records={};
    const job={tab:null,sending:false};
    const chrome={storage:{local:{
      async get(key){lastActivity=now;return {[key]:records[key]};},
      async set(values){lastActivity=now;Object.assign(records,values);},
    }},runtime:{onMessage:{addListener(){}}},tabs:{
      async create(){lastActivity=now;return {id:7};},
      async sendMessage(_tab,message){
        lastActivity=now;
        if(message.type==='project:ready') return {ready:true};
        // Model verification + upload can exceed the worker's idle lifetime.
        for(now=1000;now<=65000;now+=1000){
          if(now-lastActivity>=30000) throw Error('MV3 worker suspended during upload');
          for(const timer of timers.values()) if(now>=timer.next){
            timer.next+=timer.ms;timer.callback();await Promise.resolve();
          }
        }
        if(outcome==='throw') throw Error('Page closed');
        job.cancelled=outcome==='cancelled';
        job.sending=['submitted','uncertain'].includes(outcome);
        return {sent:outcome==='submitted',reason:'fixture failure'};
      },
    }};
    const context={chrome,importScripts(){},setTimeout,Date:{now:()=>now},
      setInterval(callback,ms){const id=++nextId;timers.set(id,{callback,ms,next:now+ms});return id;},
      clearInterval(id){timers.delete(id);}};
    vm.runInNewContext(source+'\nglobalThis.testRun=run;',context);
    await context.testRun('receipt','offline fixture',job);
    assert.ok(now>=65000,'Worker must survive upload rather than fail at 30 seconds');
    assert.equal(timers.size,0,'Keepalive must stop after success, error or cancellation');
    if(outcome==='cancelled') assert.equal(records['upload:receipt'],undefined);
    else assert.equal(records['upload:receipt'].state,outcome==='throw'?'failed':outcome);
  }
});
