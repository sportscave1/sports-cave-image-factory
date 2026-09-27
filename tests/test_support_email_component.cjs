// Pure UI boundary helpers. End-to-end layout is checked with the local mock harness.
const assert=require('node:assert/strict');
const {esc,size,safeLink,locked}=require('../components/support_email/mail.js');
assert.equal(esc('<img src=x onerror="x">'), '&lt;img src=x onerror=&quot;x&quot;&gt;');
assert.equal(safeLink('javascript:alert(1)'), '');
assert.equal(safeLink('https://user:password@example.test'), '');
assert.equal(safeLink('https://example.test/path'), 'https://example.test/path');
assert.equal(size(1800000), '1.7 MB');
for (const status of ['accepted','unknown','in_progress']) assert.equal(locked({send_result:{status}}),true);
assert.ok(!locked({send_result:{status:'rejected'}}));
assert.equal(locked({send_result:{},draft_pending:true}),true);
console.log('Email component helper checks passed (10 assertions).');
