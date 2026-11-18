const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const id='00000000-0000-0000-0000-000000000001';
const chat='https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/c/'+id;
function fixture(records=new Map()) {
  const calls=[],opens=[],messages=[];
  const job={id,receipt:'a'.repeat(64),chat_url:chat,missing:['ad_copy.csv']};
  let downloads=[],valid=true;
  const chrome={runtime:{onStartup:{addListener(){}},onInstalled:{addListener(){}}},
    alarms:{onAlarm:{addListener(){}}},
    tabs:{get:async()=>({id:1,url:chat}),query:async()=>[],create:async options=>{opens.push(options);return {id:1,...options};},
      update:async()=>{},sendMessage:async(tab,message)=>{messages.push(message);return {clicked:true,response:'response-1',chat};}},
    downloads:{search:async()=>downloads}};
  const context=vm.createContext({chrome,URL,URLSearchParams,AbortSignal,Uint8Array,Date,
    queueId:/^[a-f0-9-]{36}$/,suppliedReceipt:/^[a-f0-9]{64}$/,staffAlarm:'alarm',osOrigin:'https://os.test',
    staffRead:async key=>records.get(key),staffWrite:async(key,value)=>records.set(key,value),
    fetch:async(url,options)=>{
      calls.push({url,options});
      if(url.startsWith('https://os.test'))return {ok:true,json:async()=>({received:'ad_copy.csv'})};
      return {ok:valid,url,body:new ReadableStream({start(c){c.enqueue(new Uint8Array([1,2,3]));c.close();}})};
    }});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../windows-upload-companion/ad-queue.js'),'utf8'),context);
  context.job=job;
  return {records,calls,opens,messages,job,run:()=>vm.runInContext("collectAd(job,'paired-token')",context),
    downloads:value=>downloads=value,valid:value=>valid=value};
}
test('background tab, durable native download journal, verified receipt and no prompt resend',async()=>{
  const f=fixture();await f.run();assert.equal(f.opens[0].active,false);
  await f.run();assert.equal(f.messages.length,1);assert.equal(f.messages[0].type,'project:ad-artifact');
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
test('unrelated and ambiguous downloads never upload; expired links re-request original',async()=>{
  const f=fixture();await f.run();await f.run();
  const item={referrer:chat,filename:'ad_copy.csv',state:'complete',url:'https://files.oaiusercontent.com/original'};
  f.downloads([{...item,referrer:'https://unrelated.test'}]);await f.run();assert.equal(f.calls.length,0);
  f.downloads([item,item]);await f.run();assert.equal(f.calls.length,0);
  f.downloads([item]);f.valid(false);await f.run();assert.equal(f.records.get('publishAdJob').transfer,null);
  await f.run();assert.equal(f.messages.length,2);
});
