const assert=require('node:assert/strict');
const {mailboxCount}=require('../components/support_email/mail.js');
assert.equal(mailboxCount({error:'Connection timed out.',threads:[]}), '');
assert.equal(mailboxCount({error:'Connection timed out.',threads:[{}]}), '');
assert.equal(mailboxCount({threads:[]}), '0 conversations');
assert.equal(mailboxCount({threads:[{},{}]}), '2 conversations');
assert.equal(mailboxCount({query:'frame',threads:[{}]}), 'Search · 1 conversations');
console.log('Mailbox unavailable vs genuine empty mailbox checks passed.');
