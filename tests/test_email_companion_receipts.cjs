const assert=require('node:assert/strict');
const {companionBadge,conversationPreview,messageTime,readerStamp}=require('../components/support_email/mail.js');
for(const status of [undefined,'queued','in_progress','unknown','rejected','accepted']) {
  assert.equal(companionBadge(status?{status}:null),'');
}
const receipt={status:'sent',time:'25 Nov · 12:40 PM'};
assert.match(companionBadge(receipt),/✓ Companion sent/);
assert.match(companionBadge(receipt),/Sent automatically by Companion/);
assert.match(companionBadge(receipt),/25 Nov · 12:40 PM/);
assert.equal(conversationPreview({}),'Open conversation');
assert.equal(conversationPreview({snippet:'Question',companion:null}),'Question');
assert.match(conversationPreview({companion:receipt}),/✓ Companion sent/);
assert.match(conversationPreview({snippet:'<img onerror=boom>',companion:receipt}),/&lt;img onerror=boom&gt;/);
assert.match(messageTime({time:'Earlier',companion:receipt}),/✓ Companion sent.*<small>Earlier<\/small>/);
assert.doesNotMatch(companionBadge({status:'sent',time:'" onmouseover="boom'}),/title="[^"]*" onmouseover=/);
assert.notEqual(readerStamp({messages:[{key:'a'}]}),readerStamp({messages:[{key:'a',companion:receipt}]}));
console.log('Companion send attribution, escaping and reader refresh checks passed (16 assertions).');
