const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {test}=require('node:test');
function fixture({finished=false,blocked=false}={}) {
  const id='00000000-0000-0000-0000-000000000001',receipt='a'.repeat(64);
  const records=new Map([['staffQueueCredential','x'.repeat(43)],['staffQueueJob',{id,receipt,tab:1,chatTab:2}],
    ['upload:'+receipt,{state:'submitted',time:1}]]);
  const messages=[],removed=[];
  const chat='https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/c/00000000-0000-0000-0000-000000000002';
  let reply={stop:{id}},events;
  const chrome={runtime:{getManifest:()=>({version:'1.3.4'}),onMessage:{addListener(){}},onStartup:{addListener(){}},onInstalled:{addListener(){}}},
    alarms:{onAlarm:{addListener(){}},get:async()=>null,create:async()=>{}},
    storage:{local:{get:async key=>({[key]:records.get(key)}),set:async values=>Object.entries(values).forEach(([key,value])=>records.set(key,value))}},
    tabs:{get:async tab=>({id:tab,url:tab===2 ? chat : 'https://sports-cave-image-factory.onrender.com/?staff_upload_job='+id}),
      sendMessage:async(tab,message)=>{messages.push({tab,...message});return message.type==='project:cancel'?{stopped:true}:
        {finished,blocked,reason:blocked?'ChatGPT error: Network error':'',activity:'stable',chat_url:chat};},
      remove:async tab=>removed.push(tab),reload:async()=>{}}};
  const ctx=vm.createContext({chrome,URL,AbortSignal,Date,setTimeout,clearTimeout,fetch:async(_,options)=>{
    events=JSON.parse(options.body);return {ok:true,json:async()=>reply};}});
  ctx.importScripts=file=>vm.runInContext(fs.readFileSync('windows-upload-companion/'+file,'utf8'),ctx);
  ctx.importScripts('worker.js');
  return {id,receipt,records,messages,removed,events:()=>events,respond:value=>reply=value,run:code=>vm.runInContext(code,ctx)};
}
test('server cancellation stops only the owned ChatGPT response and upload tab, and journals cancellation',async()=>{
  const f=fixture();await f.run('staffQueueTick()');
  assert.deepEqual(f.messages.filter(m=>m.type==='project:cancel').map(m=>m.tab),[2]);
  assert.deepEqual(f.removed,[1]);
  assert.equal(f.records.get('upload:'+f.receipt).state,'cancelled');
  assert.equal(f.records.get('staffQueueJob'),null);
});
test('completed but unverified conversation remains available for verification',async()=>{
  const f=fixture({finished:true});f.respond({job:{id:f.id,stage:5}});
  await f.run('staffQueueTick()');
  f.records.get('staffQueueJob').idleSince=Date.now()-4*60*1000;
  await f.run('staffQueueTick()');
  assert.equal(f.events().state,'submitted');
});
test('live ChatGPT errors propagate to the server',async()=>{
  const f=fixture({blocked:true});f.respond({});await f.run('staffQueueTick()');
  assert.equal(f.events().state,'blocked');assert.match(f.events().reason,/Network error/);
});
