const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function main() {
  let onMessage;
  const chrome = {
    runtime: {getManifest: () => ({version:'1.0.6'}),onMessage: {addListener: listener => { onMessage = listener; }}},
    storage: {local: {get: async key => ({[key]: {state: key.startsWith('upload:') ? 'submitted' : 'ready'}})}},
  };
  const source = fs.readFileSync(path.join(__dirname, '../windows-upload-companion/worker.js'), 'utf8');
  vm.runInNewContext(source, {chrome, URL});

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
      const approved = await invoke({type:'project:permit',id:message.id}, {url:opened[0],frameId:0,tab:{id:tabId}});
      assert.equal(approved.ok,true);
      sent.push(message.prompt);
      return {sent:true};
    },
  };
  const request = {type:'os:start',receipt:'b'.repeat(64),prompt:longPrompt};
  assert.equal((await invoke(request,bridge)).accepted,true);
  assert.equal((await invoke(request,bridge)).accepted,true);
  await submitted;
  assert.equal((await invoke(request,bridge)).accepted,true);
  assert.deepEqual(opened,['https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project']);
  assert.deepEqual(sent,[longPrompt]);
  assert.equal((await invoke({type:'os:health',receipt:request.receipt},bridge)).state,'submitted');
  assert.equal((await invoke({type:'os:health',receipt:'c'.repeat(64)},bridge)).state,'ready');
  console.log('Upload Companion accepts the live Streamlit iframe URL and rejects other origins, paths and top-level frames.');
}
main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
