const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function main() {
  let onMessage;
  let alarm;
  let fetchQueue;
  const chrome = {
    runtime: {getManifest: () => ({version:'1.1.0'}),onMessage: {addListener: listener => { onMessage = listener; }},
      onInstalled:{addListener(){}},onStartup:{addListener(){}}},
    storage: {local: {get: async key => ({[key]: {state: key.startsWith('upload:') ? 'submitted' : 'ready'}})}},
    alarms:{get:async()=>alarm,create:async name=>{alarm={name};},onAlarm:{addListener(){}}},
  };
  const context = vm.createContext({chrome, URL, AbortSignal, setTimeout, setInterval, clearInterval, crypto:require('node:crypto').webcrypto, atob, Uint8Array, fetch:(...args)=>fetchQueue(...args)});
  context.importScripts = file => vm.runInContext(fs.readFileSync(path.join(__dirname,'../windows-upload-companion',file),'utf8'),context);
  context.importScripts('worker.js');
  const raw=Buffer.from('original reference bytes');
  const reference={name:'fixture-black.webp',type:'image/webp',size:raw.length,data:raw.toString('base64'),
    sha256:require('node:crypto').createHash('sha256').update(raw).digest('hex')};
  assert.equal(await context.verifiedReference(reference),true);
  assert.equal(await context.verifiedReference({...reference,data:Buffer.from('damaged reference bytes').toString('base64')}),false);
  assert.equal(await context.verifiedReference({...reference,size:raw.length+1}),false);
  assert.equal(await context.verifiedReference({...reference,name:'../fixture.webp'}),false);

  function health(url, frameId = 1) {
    return new Promise(resolve => {
      if (!onMessage({type: 'os:health'}, {url, frameId, tab: {id: 4}}, resolve)) resolve();
    });
  }
  const origin = 'https://sports-cave-image-factory.onrender.com';
  const page = origin + '/component/product_upload_gallery.product_upload_gallery/index.html';
  assert.equal((await health(page)).state, 'ready');
  assert.equal((await health(page + '?streamlitUrl=' + encodeURIComponent(origin + '/'))).state, 'ready');
  assert.equal(await health(page, 0), undefined);
  assert.equal(await health(page.replace('onrender.com', 'onrender.com.example.org')), undefined);
  assert.equal(await health(page.replace('index.html', 'app.js')), undefined);
  assert.equal(await health(origin + '/?streamlitUrl=' + encodeURIComponent(page)), undefined);
  const longPrompt = 'Run this Product Uploads workflow for Example. https://www.dropbox.com/home/Test ' +
    'STEP 5 — VERIFY EDITION OPS AND ATTACH THE ORIGINAL PSD ' + 'scene '.repeat(23000);
  const start = prompt => new Promise(resolve => {
    onMessage({type: 'os:start', receipt: 'a'.repeat(64), prompt}, {url: page, frameId: 1, tab: {id: 4}}, resolve);
  });
  assert.ok(longPrompt.length > 131072);
  assert.equal((await start(longPrompt)).accepted, true);
  assert.equal((await start(longPrompt + 'x'.repeat(1048576))).accepted, false);

  const records = new Map(), opened = [], sent = [];
  const tabId = 12;
  const bridge = {url: page + '?streamlitUrl=' + encodeURIComponent(origin + '/'), frameId: 1, tab: {id: 4}};
  const invoke = (message, sender) => new Promise(resolve => onMessage(message, sender, resolve));
  let finish;
  const submitted = new Promise(resolve => { finish = resolve; });
  chrome.storage.local = {
    get: async key => ({[key]: records.get(key)}),
    set: async values => {
      for (const [key, record] of Object.entries(values)) records.set(key, record);
      if (values.uploadCompanionLast?.state === 'submitted') finish();
    },
  };
  chrome.tabs = {
    create: async ({url}) => { opened.push(url); return {id: tabId}; },
    sendMessage: async (_tab, message) => {
      if (message.type === 'project:ready') return {ready: true};
      assert.equal(message.freshUpload,true);
      assert.deepEqual(message.reference,reference);
      assert.equal((await invoke({type:'project:backup-draft',id:message.id,text:'Preserved unsent draft'},
        {url:opened[0],frameId:0,tab:{id:tabId+999}})).ok,false);
      assert.equal((await invoke({type:'project:backup-draft',id:message.id,text:'Preserved unsent draft'},
        {url:opened[0],frameId:0,tab:{id:tabId}})).ok,true);
      assert.equal(records.get('draft:'+message.id).text,'Preserved unsent draft');
      const approved = await invoke({type:'project:permit',id:message.id}, {url:opened[0],frameId:0,tab:{id:tabId}});
      assert.equal(approved.ok,true);
      sent.push(message.prompt);
      return {sent:true};
    },
  };
  const request = {type:'os:start',receipt:'b'.repeat(64),prompt:longPrompt,reference};
  assert.equal((await invoke({...request,reference:{...reference,sha256:'0'.repeat(64)}},bridge)).accepted,false);
  assert.equal(opened.length,0);
  assert.equal((await invoke(request,bridge)).accepted,true);
  assert.equal((await invoke(request,bridge)).accepted,true);
  await submitted;
  assert.equal((await invoke(request,bridge)).accepted,true);
  assert.deepEqual(opened,['https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project']);
  assert.deepEqual(sent,[longPrompt]);
  assert.equal((await invoke({type:'os:health',receipt:request.receipt},bridge)).state,'submitted');
  assert.equal((await invoke({type:'os:health',receipt:'c'.repeat(64)},bridge)).state,'ready');
  const queued = '33441519-3951-40f3-a5d7-e2edb528e5a7';
  const credential = 'a'.repeat(43);
  const requests = [];
  let connected = false;
  let claim = {id:queued,stage:1};
  fetchQueue = async (url, options) => {
    assert.equal(url, origin + '/api/staff-product-uploads/tick');
    assert.equal(options.headers.Authorization,'Bearer '+credential);
    requests.push(JSON.parse(options.body));
    if (!connected) throw new Error('Offline');
    return {ok:true,json:async()=>({job:claim})};
  };
  const tabs = [];
  chrome.tabs.create = async options => {
    tabs.push(options);
    return {id:tabId + tabs.length};
  };
  chrome.tabs.get = async id => ({url:tabs[id-tabId-1].url});
  await context.pairStaffQueue(credential);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(tabs.length,0);
  assert.ok(alarm);
  connected = true;
  assert.equal((await invoke({type:'os:wake'},bridge)).paired,true);
  await new Promise(resolve => setImmediate(resolve));
  await context.staffQueueTick();
  assert.equal(tabs.length,1);
  assert.equal(tabs[0].active,false);
  assert.equal(new URL(tabs[0].url).searchParams.get('staff_upload_job'),queued);
  assert.equal((await invoke({...request,staffJob:queued},bridge)).accepted,false);
  assert.equal(await context.rememberStaffReceipt(queued,request.receipt,tabId+1),true);
  claim = {...claim,stage:5};
  await context.staffQueueTick();
  assert.equal(requests.at(-1).state,'submitted');
  assert.equal(tabs.length,1);
  // A server-authorised manual reset has a fresh delivery ID. The installed
  // companion opens it despite the previous tab and submitted receipt.
  const retryJob='8a89bf11-c607-4995-9361-acd988272cbc';
  claim={id:retryJob,stage:1};
  await context.staffQueueTick();
  assert.equal(tabs.length,2);
  assert.equal(new URL(tabs[1].url).searchParams.get('staff_upload_job'),retryJob);
  assert.equal(await context.rememberStaffReceipt(queued,'d'.repeat(64),tabId+1),false);
  assert.equal(await context.rememberStaffReceipt(retryJob,'d'.repeat(64),tabId+2),true);
  console.log('Upload Companion accepts the live Streamlit iframe URL and rejects other origins, paths and top-level frames.');
}
const watchdog = setTimeout(() => { console.error('Companion test did not finish'); process.exit(1); }, 10000);
main().finally(() => clearTimeout(watchdog)).catch(error => {
  console.error(error);
  process.exitCode = 1;
});
