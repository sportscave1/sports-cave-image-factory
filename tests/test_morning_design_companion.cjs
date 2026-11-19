const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

function fixture(records = new Map()) {
  const listeners = [], opened = [], sent = [], tabs = new Map();
  let result = {jobs:[]}, events;
  const chrome = {
    runtime:{id:'companion',getManifest:()=>({version:'1.2.0'}),onMessage:{addListener:fn=>listeners.push(fn)},
      onStartup:{addListener(){}},onInstalled:{addListener(){}}},
    alarms:{get:async()=>null,create:async()=>{},onAlarm:{addListener(){}}},
    storage:{local:{get:async key=>({[key]:records.get(key)}),set:async values=>{
      for (const [key,value] of Object.entries(values)) records.set(key,value);
    }, remove:async key=>records.delete(key)}},
    tabs:{
      create:async ({url,active})=>{const tab={id:opened.length+1,url,active};opened.push(tab);tabs.set(tab.id,tab);return tab;},
      get:async id=>tabs.get(id),
      sendMessage:async (id,message)=>{
        if(message.type==='project:ready')return {ready:true};
        if(message.type==='project:progress')return {blocked:false,chat_url:job(1).project.replace('/project','/c/00000000-0000-0000-0000-000000000099')};
        const sender={url:tabs.get(id).url,frameId:0,tab:{id}};
        const permission=await new Promise(resolve=>listeners[0]({type:'project:permit',id:message.id},sender,resolve));
        assert.equal(permission.ok,true);
        sent.push(message);
        return {sent:true};
      },
    },
  };
  const context=vm.createContext({chrome,URL,AbortSignal,setTimeout,clearTimeout,setInterval,clearInterval,
    fetch:async (_url,options)=>{events=JSON.parse(options.body);return {ok:true,json:async()=>result};}});
  context.importScripts=file=>vm.runInContext(fs.readFileSync(path.join(__dirname,'../windows-upload-companion',file),'utf8'),context);
  context.importScripts('worker.js');
  records.set('staffQueueCredential','x'.repeat(43));
  return {records,opened,sent,events:()=>events,respond:value=>{result=value;},
    run:code=>vm.runInContext(code,context)};
}
function job(n) {
  const id=`00000000-0000-0000-0000-${String(n).padStart(12,'0')}`;
  return {id,stage:1,project:'https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project',
    receipt:String(n).repeat(64),prompt:`The exact design prompt. morning_design_job_id = "${id}"`};
}

test('one design submits through the existing mutex and never resubmit on repeated ticks or restart',async()=>{
  const f=fixture(), jobs=[job(1)];
  f.respond({enabled:true,jobs});
  await f.run('designQueueTick()');
  await f.run('queue');
  assert.equal(f.sent.length,1);
  assert.equal(f.opened.length,1);
  assert.equal(Object.keys(f.records.get('morningDesignJobs')).length,1);
  assert.equal(Object.values(f.records.get('morningDesignJobs')).filter(j=>j.tab).length,1);
  await f.run('designQueueTick()');
  await f.run('queue');
  assert.equal(f.sent.length,1);
  assert.equal(f.events().events.filter(e=>e.state==='submitted').length,1);
  assert.ok(f.events().events[0].chat_url.endsWith('/c/00000000-0000-0000-0000-000000000099'));
  const restart=fixture(f.records);
  restart.respond({jobs});
  await restart.run('designQueueTick()');
  await restart.run('queue');
  assert.equal(restart.sent.length,0);
});

test('requests one slot and never opens two new design chats from an older server response',async()=>{
  const f=fixture(), jobs=[job(1),job(2)];
  f.respond({enabled:true,jobs});
  await f.run('designQueueTick()');await f.run('queue');
  assert.equal(f.events().capacity,1);
  assert.equal(f.sent.length,1);
  assert.equal(f.opened.length,1);
  f.respond({enabled:true,jobs:[{...jobs[0],stage:2},jobs[1]]});
  await f.run('designQueueTick()');await f.run('queue');
  assert.equal(f.sent.length,1,'a running design prevents opening another');
});

test('continues reporting two already submitted jobs without opening any replacement chat',async()=>{
  const f=fixture(), jobs=[{...job(1),stage:2},{...job(2),stage:2}];
  const saved={};
  for(const j of jobs){
    f.records.set('upload:'+j.receipt,{state:'submitted'});
    saved[j.id]={id:j.id,receipt:j.receipt};
  }
  f.records.set('morningDesignJobs',saved);
  f.respond({enabled:true,jobs});
  await f.run('designQueueTick()');await f.run('queue');
  assert.equal(f.events().capacity,1);
  assert.equal(f.events().events.length,2);
  assert.equal(f.sent.length,0);
  assert.equal(Object.keys(f.records.get('morningDesignJobs')).length,2);
});

test('persisted sending state after restart is reported uncertain, without opening another chat',async()=>{
  const f=fixture(), j=job(1);
  f.records.set('upload:'+j.receipt,{state:'sending'});
  f.records.set('morningDesignJobs',{[j.id]:{id:j.id,receipt:j.receipt,tab:99}});
  f.respond({jobs:[j]});
  await f.run('designQueueTick()');
  assert.equal(f.events().events[0].state,'uncertain');
  assert.equal(f.opened.length,0);
});

test('invalid project or changed job correlation cannot open or submit a chat',async()=>{
  const f=fixture(), j=job(1);
  f.respond({jobs:[{...j,project:'https://chatgpt.com/'}]});
  await f.run('designQueueTick()');
  f.respond({jobs:[{...j,prompt:'Uncorrelated prompt'}]});
  await f.run('designQueueTick()');
  assert.equal(f.opened.length,0);
});

test('queued edit submits its unchanged prompt once without a new-design receipt',async()=>{
  const f=fixture(),j={...job(1),kind:'edit',prompt:'**USER-REQUESTED DESIGN CHANGES**\nFix spacing\n\nEXACT EXISTING EDIT PROMPT'};
  f.respond({jobs:[j]});await f.run('designQueueTick()');await f.run('queue');
  assert.equal(f.sent[0].prompt,j.prompt);
  await f.run('designQueueTick()');await f.run('queue');
  assert.equal(f.sent.length,1);
});


test('a second queued design starts only when the server advances after completion or failure',async()=>{
  const f=fixture();
  f.respond({jobs:[job(1)]});
  await f.run('designQueueTick()'); await f.run('queue');
  f.respond({jobs:[{...job(1),stage:2}]});
  await f.run('designQueueTick()'); await f.run('queue');
  assert.equal(f.sent.length,1);
  f.respond({jobs:[job(2)]});
  await f.run('designQueueTick()'); await f.run('queue');
  assert.equal(f.sent.length,2);
  assert.deepEqual(Object.keys(f.records.get('morningDesignJobs')),[job(2).id]);
});

test('the ad queue opens a background project once and reports a matching receipt', async () => {
  const f = fixture();
  const id = job(1).id;
  const ad = {id,stage:'opening',receipt:'a'.repeat(64),
              project:'https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/project',
              prompt:'Sports Cave automatic ad job '+id+'\nGenerate the ad.'};
  f.respond({job:ad});
  await f.run('adQueueTick()');
  await f.run('queue');
  assert.equal(f.opened[0].active,false);
  assert.equal(f.sent[0].prompt,ad.prompt);
  await f.run('adQueueTick()');
  await f.run('queue');
  assert.equal(f.events().id,id);
  assert.equal(f.events().state,'submitted');
  assert.equal(f.opened.length,1);
  f.respond({});
  await f.run('adQueueTick()');
  assert.equal(f.records.has('publishAdJob'),false);
});

test('an explicitly requeued design uses a fresh receipt and submits exactly once',async()=>{
  const f=fixture(), original=job(1);
  f.respond({jobs:[original]});
  await f.run('designQueueTick()'); await f.run('queue');
  f.respond({jobs:[]});
  await f.run('designQueueTick()');
  const retry={...original,receipt:'a'.repeat(64)};
  f.respond({jobs:[retry]});
  await f.run('designQueueTick()'); await f.run('queue');
  assert.equal(f.sent.length,2);
  await f.run('designQueueTick()'); await f.run('queue');
  assert.equal(f.sent.length,2);
});
