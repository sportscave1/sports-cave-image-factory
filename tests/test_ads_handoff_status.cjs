const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const id='00000000-0000-0000-0000-000000000001';
const chat='https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/c/'+id;
async function tick(state,progress,{url=chat,bound,missing=false}={}) {
  const records=new Map([['device','token'],['publishAdJob',{id,receipt:'a'.repeat(64),tab:7,chat_url:bound}]]);
  const saves=[],events=[],messages=[];
  const c=vm.createContext({URL,Date,AbortSignal,setInterval:()=>1,clearInterval(){},
    staffDeviceKey:'device',staffAlarm:'alarm',osOrigin:'https://fixture.test',
    staffRead:async k=>records.get(k),staffWrite:async(k,v)=>records.set(k,v),
    health:async()=>({state,reason:'old uncertainty'}),save:async(...args)=>saves.push(args),
    companionMessage:async(tab,msg)=>{messages.push(msg.type);if(progress instanceof Error)throw progress;return progress;},
    fetch:async(url,options)=>{events.push(JSON.parse(options.body));return {ok:true,json:async()=>({busy:true})};},
    chrome:{tabs:{get:async()=>missing?null:{id:7,url}},storage:{local:{get:async()=>({})}},
      alarms:{onAlarm:{addListener(){}}},runtime:{onStartup:{addListener(){}},onInstalled:{addListener(){}}}}});
  vm.runInContext(fs.readFileSync('windows-upload-companion/ad-queue.js','utf8'),c);
  await vm.runInContext('adQueueTick()',c);
  return {events,saves,messages,records};
}
test('missed send receipt recovers while thinking without another Send',async()=>{
  for(const state of ['uncertain','sending']) {
    const f=await tick(state,{chat_url:chat,generating:true,finished:false,activity:'0'});
    assert.equal(f.events[0].state,'submitted');assert.equal(f.events[0].generating,true);
    assert.equal(f.records.get('publishAdJob').chat_url,chat);
    assert.equal(f.saves.length,1);assert.deepEqual(f.messages,['project:progress']);
  }
});
test('late completed response reports the actual blocker and saves its chat',async()=>{
  const f=await tick('uncertain',{chat_url:chat,finished:true,generating:false,blocked:true,reason:'Safety rejection'});
  assert.equal(f.events[0].state,'blocked');assert.equal(f.events[0].reason,'Safety rejection');
  assert.equal(f.events[0].chat_url,chat);
});
test('missing or interrupted browser contact remains unconfirmed, never resends',async()=>{
  for(const options of [{missing:true},{url:'https://example.test/'}]) {
    const f=await tick('uncertain',null,options);
    assert.equal(f.events[0].state,'uncertain');assert.equal(f.saves.length,0);
  }
  const f=await tick('uncertain',new Error('disconnected'));
  assert.equal(f.events[0].state,'uncertain');assert.equal(f.saves.length,0);
});
test('a tab navigated away from its bound chat cannot attach unrelated progress',async()=>{
  const f=await tick('uncertain',{chat_url:chat,finished:true},{bound:chat.slice(0,-1)+'9'});
  assert.equal(f.events[0].state,'uncertain');assert.equal(f.events[0].chat_url,undefined);
  assert.equal(f.saves.length,0);
});
