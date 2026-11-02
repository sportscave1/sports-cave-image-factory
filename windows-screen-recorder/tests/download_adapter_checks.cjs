// Offline worker-contract checks; not browser/Save As acceptance.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../edge-adapter/downloads.js'), 'utf8');
function run(error, id, origin = 'http://127.0.0.1:18963') {
  const warnings = [], requests = [];
  let listener;
  const chrome = {
    runtime: { lastError: error, onMessage: {addListener: f => listener = f} },
    downloads: {
      onCreated: {addListener() {}}, onChanged: {addListener() {}},
      download: (request, callback) => { requests.push(request); callback(id); }
    }
  };
  vm.runInNewContext(source, {chrome, URL, console: {warn: x => warnings.push(x)}});
  listener({kind:'save_as', url:origin+'/sample.txt?sc_download=12345678-1234-1234-1234-123456789012', filename:'disposable.txt'}, {url:origin+'/tab-a'});
  return {warnings, requests};
}
assert.equal(run(null, 42).warnings.length, 0);
assert.equal(run({message:'private destination'}, undefined).warnings.length, 1);
assert.ok(!run({message:'private destination'}, undefined).warnings[0].includes('private destination'));
assert.equal(run(null, undefined).warnings.length, 1);
assert.equal(run(null, 42, 'https://unapproved.example').requests.length, 0);
assert.equal(run(null, 42).requests[0].saveAs, true);
assert.equal(run(null, 42).requests[0].conflictAction, 'uniquify');
console.log('PASS: 7 offline Save As adapter contract checks (no browser acceptance claimed).');
