const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const id='00000000-0000-0000-0000-000000000001';
const chat='https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/c/'+id;
function fixture(records=new Map()) {
  const calls=[],opens=[],messages=[],reloads=[];
  const job={id,receipt:'a'.repeat(64),chat_url:chat,missing:['ad_copy.csv']};
  let downloads=[],valid=true,downloadError='';
  const chrome={runtime:{onStartup:{addListener(){}},onInstalled:{addListener(){}}},
    alarms:{onAlarm:{addListener(){}}},
    tabs:{get:async()=>({id:1,url:chat}),query:async()=>[],create:async options=>{opens.push(options);return {id:1,...options};},
      update:async()=>{},reload:async tab=>reloads.push(tab),sendMessage:async(tab,message)=>{messages.push(message);return message.type==='project:ad-download-status'?{error:downloadError}:{clicked:true,response:'response-1',chat};}},
    downloads:{search:async()=>downloads}};
  const context=vm.createContext({chrome,setTimeout,clearTimeout,URL,URLSearchParams,AbortSignal,Uint8Array,Date,
    queueId:/^[a-f0-9-]{36}$/,suppliedReceipt:/^[a-f0-9]{64}$/,staffAlarm:'alarm',osOrigin:'https://os.test',
    staffRead:async key=>records.get(key),staffWrite:async(key,value)=>records.set(key,value),
    fetch:async(url,options)=>{
      calls.push({url,options});
      if(url.startsWith('https://os.test'))return {ok:true,json:async()=>({received:'ad_copy.csv'})};
      return {ok:valid,url,body:new ReadableStream({start(c){c.enqueue(new Uint8Array([1,2,3]));c.close();}})};
    }});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../windows-upload-companion/message-deadline.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../windows-upload-companion/ad-queue.js'),'utf8'),context);
  context.job=job;
  return {records,calls,opens,messages,reloads,job,run:()=>vm.runInContext("collectAd(job,'paired-token')",context),
    downloads:value=>downloads=value,valid:value=>valid=value,downloadError:value=>downloadError=value};
}
test('background tab, durable native download journal, verified receipt and no prompt resend',async()=>{
  const f=fixture();await f.run();assert.equal(f.opens[0].active,false);
  await f.run();assert.equal(f.messages.length,1);assert.equal(f.messages[0].type,'project:ad-artifact');
  assert.equal(f.messages[0].chat,chat);
  const restart=fixture(f.records);
  restart.downloads([{referrer:'https://chatgpt.com/',filename:'C:\\Downloads\\ad_copy (1).csv',state:'in_progress',url:'https://files.oaiusercontent.com/original'}]);
  await restart.run();assert.equal(restart.calls.length,0);
  restart.downloads([{referrer:chat,filename:'C:\\Downloads\\ad_copy (1).csv',state:'complete',url:'https://files.oaiusercontent.com/original'}]);
  await restart.run();assert.equal(restart.messages.length,0);assert.equal(restart.calls.length,2);
  assert.equal(restart.calls[1].options.headers.Authorization,'Bearer paired-token');
  assert.equal(restart.calls[0].options.headers,undefined);
  assert.equal(restart.records.get('publishAdJob').transfer,null);
  restart.job.missing=[];await restart.run();assert.equal(restart.calls.length,2);
});
test('Play reloads the saved background chat once and pins recovered response IDs',async()=>{
  const f=fixture();f.job.resume_token='new-resume';f.job.recover=true;f.job.response_ids={'ad_copy.csv':'original-response'};
  await f.run();await f.run();assert.deepEqual(f.reloads,[1]);
  await f.run();assert.equal(f.messages[0].recover,true);assert.equal(f.messages[0].response,'original-response');
  await f.run();assert.equal(f.reloads.length,1);
});
test('unrelated and ambiguous downloads never upload; expired links re-request original',async()=>{
  const f=fixture();await f.run();await f.run();
  const item={referrer:chat,filename:'ad_copy.csv',state:'complete',url:'https://files.oaiusercontent.com/original'};
  f.downloads([{...item,referrer:'https://unrelated.test'}]);await f.run();assert.equal(f.calls.length,0);
  f.downloads([item,item]);await f.run();assert.equal(f.calls.length,0);
  f.downloads([item]);f.valid(false);await f.run();assert.equal(f.records.get('publishAdJob').transfer,null);
  await f.run();assert.equal(f.messages.filter(m=>m.type==='project:ad-artifact').length,2);
});

test('provider download failures refresh twice then stop across worker restarts; Resume resets budget',async()=>{
  let f=fixture();await f.run();
  const records=f.records;
  for(let attempt=1;attempt<=3;attempt++) {
    f=fixture(records);f.downloadError('ChatGPT could not download ad_copy.csv');
    await f.run();await f.run();
    assert.equal(records.get('publishAdJob').downloadFailures,attempt);
    assert.equal(f.reloads.length,attempt<3?1:0);
    assert.equal(f.calls.length,0);
  }
  assert.equal(records.get('publishAdJob').transferFailed,true);
  const count=f.messages.length;await f.run();assert.equal(f.messages.length,count);
  f.job.resume_token='restored-files';await f.run();
  assert.equal(records.get('publishAdJob').transferFailed,false);
  assert.equal(records.get('publishAdJob').downloadFailures,0);
  await f.run();assert.equal(f.messages.at(-1).type,'project:ad-artifact');
});

test('silent missing receipts have the same bounded retry budget',async()=>{
  const f=fixture();await f.run();await f.run();
  for(let attempt=1;attempt<=3;attempt++) {
    f.records.get('publishAdJob').transfer.started='2000-01-01T00:00:00Z';
    await f.run();
    if(attempt<3)await f.run();
  }
  assert.equal(f.records.get('publishAdJob').transferFailed,true);
  assert.equal(f.calls.length,0);
});

test('expired blob after a restart retries the original attachment instead of remaining stuck',async()=>{
  const f=fixture();await f.run();await f.run();
  f.downloads([{referrer:chat,filename:'ad_copy.csv',state:'complete',url:'blob:https://chatgpt.com/expired'}]);
  await f.run();
  assert.equal(f.messages.at(-1).type,'project:ad-blob');
  assert.equal(f.messages.at(-1).chat,chat);
  assert.equal(f.records.get('publishAdJob').transfer,null);
  assert.equal(f.calls.length,0);
  await f.run();
  assert.equal(f.messages.at(-1).type,'project:ad-artifact');
});
