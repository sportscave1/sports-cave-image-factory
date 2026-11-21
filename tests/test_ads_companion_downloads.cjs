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
  let downloads=[],valid=true,downloadError='',claim=null,staged=false,library=null,libraryReady=true,libraryDelay=0;
  let now=Date.now();
  const ClockDate=class extends Date {constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}};
  const chrome={runtime:{onStartup:{addListener(){}},onInstalled:{addListener(){}}},
    alarms:{onAlarm:{addListener(){}}},
    tabs:{get:async id=>({id,url:opens[id-1]?.url||chat}),query:async()=>[],create:async options=>{opens.push(options);return {id:opens.length,...options};},
      update:async()=>{},reload:async tab=>reloads.push(tab),sendMessage:async(tab,message)=>{messages.push(message);if(message.type==='project:ad-library')now+=libraryDelay;return message.type==='project:ad-download-status'?{error:downloadError}:message.type==='project:ad-repair-status'?{ready:true,found:false,staged}:{clicked:message.type==='project:ad-library'?libraryReady:true,response:'response-1',chat,library};}},
    downloads:{search:async()=>downloads}};
  const context=vm.createContext({chrome,setTimeout,clearTimeout,URL,URLSearchParams,AbortSignal,Uint8Array,Date:ClockDate,
    queueId:/^[a-f0-9-]{36}$/,suppliedReceipt:/^[a-f0-9]{64}$/,staffAlarm:'alarm',osOrigin:'https://os.test',
    staffRead:async key=>records.get(key),staffWrite:async(key,value)=>records.set(key,value),
    fetch:async(url,options)=>{
      calls.push({url,options});
      if(url.endsWith('/ad-tick') && claim)return claim();
      if(url.startsWith('https://os.test'))return {ok:true,json:async()=>({received:'ad_copy.csv'})};
      return {ok:valid,url,body:new ReadableStream({start(c){c.enqueue(new Uint8Array([1,2,3]));c.close();}})};
    }});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../windows-upload-companion/message-deadline.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../windows-upload-companion/ad-queue.js'),'utf8'),context);
  context.job=job;
  return {records,calls,opens,messages,reloads,job,run:()=>vm.runInContext("collectAd(job,'paired-token')",context),
    downloads:value=>downloads=value,valid:value=>valid=value,downloadError:value=>downloadError=value,claim:value=>claim=value,
    staged:value=>staged=value,library:value=>library=value,libraryReady:value=>libraryReady=value,libraryDelay:value=>libraryDelay=value,now:()=>now};
}

test('a Library viewer without a Download button exhausts the same retry budget',async()=>{
  const f=fixture();await f.run();f.library('https://chatgpt.com/library?file_id=libfile_123abc');f.libraryReady(false);
  for(let attempt=1;attempt<=3;attempt++) {
    await f.run();
    f.records.get('publishAdJob').transfer.started='2000-01-01T00:00:00Z';
    await f.run(); // open its Library original
    await f.run(); // no ready Download button
    f.records.get('publishAdJob').transfer.libraryOpenedAt='2000-01-01T00:00:00Z';
    await f.run();
    assert.equal(f.records.get('publishAdJob').downloadFailures,attempt);
  }
  assert.equal(f.records.get('publishAdJob').transferFailed,true);
  assert.equal(f.calls.length,0);
});

test('a stalled native download cannot hold the queue indefinitely',async()=>{
  const f=fixture();await f.run();await f.run();
  f.downloads([{referrer:chat,filename:'ad_copy.csv',state:'in_progress',url:'https://files.oaiusercontent.com/original'}]);
  f.records.get('publishAdJob').transfer.started='2000-01-01T00:00:00Z';
  await f.run();
  assert.equal(f.records.get('publishAdJob').downloadFailures,1);
  assert.equal(f.records.get('publishAdJob').transfer,null);
});

test('a consumed permit can continue only a proven unclicked draft',async()=>{
  const f=fixture();await f.run();f.job.repair={id,state:'sending',names:['ad_copy.csv']};
  await f.run();assert.equal(f.messages.filter(m=>m.type==='project:ad-repair-send').length,0);
  f.staged(true);await f.run();
  const sent=f.messages.find(m=>m.type==='project:ad-repair-send');
  assert.equal(sent.resume,true);assert.equal(sent.permit,undefined);assert.equal(f.calls.length,0);
  assert.deepEqual(Array.from(sent.names),['ad_copy.csv']);
});

test('timestamped Library originals retain exact file and chat provenance',async()=>{
  const library='https://chatgpt.com/library?file_id=libfile_123abc';
  const f=fixture();await f.run();f.library(library);await f.run();
  f.records.get('publishAdJob').transfer.started='2000-01-01T00:00:00Z';
  await f.run();assert.equal(f.opens.at(-1).url,library);assert.equal(f.opens.at(-1).active,false);
  await f.run();assert.equal(f.messages.at(-1).type,'project:ad-library');
  assert.equal(f.records.get('publishAdJob').transfer.librarySent,true);
  f.downloads([{referrer:library,filename:'ad_copy(20261119-213046).csv',state:'complete',url:'https://files.oaiusercontent.com/original'}]);
  await f.run();assert.equal(f.calls.length,2);assert.equal(f.records.get('publishAdJob').transfer,null);
  const unrelated=fixture();await unrelated.run();unrelated.library(library);await unrelated.run();
  unrelated.downloads([{referrer:library,filename:'ad_copy(20261119-213046).csv',state:'complete',url:'https://files.oaiusercontent.com/original'}]);
  await unrelated.run();assert.equal(unrelated.calls.length,0);
});

test('only a fresh server permit can send a repair; lost claim response never resends',async()=>{
  const f=fixture();await f.run();
  f.job.repair={id,attempt:1,state:'ready',names:['ad_copy.csv']};
  let claimed=false;
  f.claim(async()=>{
    const granted=!claimed;claimed=true;
    return {ok:true,json:async()=>({job:{...f.job,repair:{...f.job.repair,state:'sending'},repair_send:granted}})};
  });
  await f.run();await f.run();
  assert.equal(f.messages.filter(m=>m.type==='project:ad-repair-send').length,1);
  assert.equal(f.messages.find(m=>m.type==='project:ad-repair-send').chat,chat);
  const restart=fixture(f.records);
  restart.job.repair={...f.job.repair,state:'sending'};
  await restart.run();assert.equal(restart.calls.length,0);
  assert.equal(restart.messages.filter(m=>m.type==='project:ad-repair-send').length,0);
  const lost=fixture();await lost.run();lost.job.repair=f.job.repair;
  lost.claim(async()=>{throw Error('reply lost after server persisted permit');});
  await assert.rejects(lost.run(),/reply lost/);
  lost.job.repair={...lost.job.repair,state:'sending'};
  await lost.run();assert.equal(lost.messages.filter(m=>m.type==='project:ad-repair-send').length,0);
});
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


test('Library receipt search begins before a fast download click, not after its reply',async()=>{
  const f=fixture();await f.run();f.library('https://chatgpt.com/library?file_id=libfile_123abc');await f.run();
  f.records.get('publishAdJob').transfer.started='2000-01-01T00:00:00Z';await f.run();
  const clickedAt=f.now();f.libraryDelay(5000);await f.run();
  assert.equal(Date.parse(f.records.get('publishAdJob').transfer.started),clickedAt);
  assert.equal(f.records.get('publishAdJob').transfer.librarySent,true);
});
