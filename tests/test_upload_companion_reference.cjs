const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const source = fs.readFileSync(require('node:path').join(__dirname, '../windows-upload-companion/composer.js'), 'utf8');

function fixture(label) {
  const files = [];
  const form = {querySelectorAll(selector) {
    if (selector === 'input[type="file"]') return [];
    return files.filter(file => selector.includes('button[aria-label^="Remove "]') ||
      selector.includes(`button[aria-label="${file.getAttribute('aria-label')}"]`) ||
      ['Remove file', 'Remove image'].some(prefix => selector.includes(`button[aria-label^="${prefix}"]`) && label.startsWith(prefix)));
  }};
  const node = {closest:()=>form, focus(){}, dispatchEvent() {
    files.push({getAttribute:()=>label, parentElement:{textContent:''}});
  }};
  let now = 0;
  const document = {querySelector: selector => selector.includes('data-message-author-role') ? null : node};
  const context = {location:{href:'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project'}, document,
    chrome:{runtime:{onMessage:{addListener(){}}}}, crypto:webcrypto, atob,
    DataTransfer:class {items={add(){}};}, File:class {}, ClipboardEvent:class {},
    Date:{now:()=>now}, setTimeout(callback, ms){now+=ms;queueMicrotask(callback);}};
  vm.runInNewContext(source.replace('  chrome.runtime.onMessage.addListener',
    '  globalThis.api={attachReference,referenceControl,attachments};\n  chrome.runtime.onMessage.addListener'), context);
  return {api:context.api,node,form,files};
}

test('Verified reference attachment recognises current ChatGPT Remove <filename> and legacy controls', async () => {
  const bytes = new TextEncoder().encode('offline image fixture');
  const reference = {name:'silver-soul-lewis-hamilton-wall-art.webp',type:'image/webp',size:bytes.length,
    data:Buffer.from(bytes).toString('base64'),sha256:Buffer.from(await webcrypto.subtle.digest('SHA-256',bytes)).toString('hex')};
  for (const label of [`Remove ${reference.name}`, 'Remove file', 'Remove image', `Remove file ${reference.name}`]) {
    const browser=fixture(label);
    assert.equal(await browser.api.attachReference(browser.node,browser.form,reference),true,label);
    assert.equal(browser.api.referenceControl(browser.form,reference),browser.files[0]);
  }
});

test('Other filenames and multiple attachments never satisfy reference verification', () => {
  const browser=fixture('Remove unrelated.webp');
  browser.node.dispatchEvent();
  assert.equal(browser.api.attachments(browser.form).length,1);
  assert.equal(browser.api.referenceControl(browser.form,{name:'expected.webp'}),null);
  browser.files.push({getAttribute:()=> 'Remove expected.webp'});
  assert.equal(browser.api.referenceControl(browser.form,{name:'expected.webp'}),null);
});


test('Only ChatGPT numeric duplicate suffixes match the verified original filename', () => {
  for(const name of ['original.webp','original(5).webp','original (12).webp']) {
    const browser=fixture('Remove '+name);browser.node.dispatchEvent();
    assert.equal(browser.api.referenceControl(browser.form,{name:'original.webp'}),browser.files[0],name);
  }
  for(const name of ['other(5).webp','original-copy.webp','original.webp.exe','original(abc).webp']) {
    const browser=fixture('Remove '+name);browser.node.dispatchEvent();
    assert.equal(browser.api.referenceControl(browser.form,{name:'original.webp'}),null,name);
  }
});
