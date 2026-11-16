const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function main() {
  let onMessage;
  const chrome = {
    runtime: {onMessage: {addListener: listener => { onMessage = listener; }}},
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
  console.log('Upload Companion accepts the live Streamlit iframe URL and rejects other origins, paths and top-level frames.');
}
main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
