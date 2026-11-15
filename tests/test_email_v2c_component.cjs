const assert=require('node:assert/strict');
const {searchKnownRows,createViewCache,readerStamp,patchReadFlags}=require('../components/support_email/mail.js');
const rows=[{key:'a',customer:'Alice',email:'a@example.test',subject:'Order SC123',recipients:'team@example.test',snippet:'Damaged frame'},
 {key:'b',customer:'Bob',email:'b@example.test',subject:'Delivery',recipients:'other@example.test',snippet:'Dispatched'}];
for(const [query,key] of [['from: alice','a'],['to: other@example.test','b'],['subject: delivery','b'],['text: damaged','a'],['SC123','a']]){
 assert.deepEqual(searchKnownRows(rows,query).map(r=>r.key),[key]);
}
assert.deepEqual(searchKnownRows(rows,'unknown'),[]);
assert.equal(searchKnownRows(rows,'').length,2);
const cache=createViewCache(2,1024);
const key=(scope,folder)=>JSON.stringify([scope,'mailbox',folder]);
cache.put(key('actor-one/session','Inbox'),rows);
assert.equal(cache.get(key('actor-two/session','Inbox')),null);
assert.equal(cache.get(key('actor-one/session','Sent')),null);
cache.clear();assert.equal(cache.get(key('actor-one/session','Inbox')),null);
console.log('Cached search prefixes, incomplete metadata matching and scoped folder keys passed.');
const before={view:'mail',messages:[{key:'a',unread:true,starred:false,reader_document:'safe'}]};
const after={...before,messages:[{...before.messages[0],unread:false,starred:true}]};
assert.equal(readerStamp(before,true),readerStamp(after,true));
assert.notEqual(readerStamp(before),readerStamp(after));
const read={dataset:{}},flag={dataset:{}};
patchReadFlags({querySelector:s=>s.includes('mark_read')?read:flag},after.messages[0]);
assert.equal(read.dataset.action,'mark_unread');assert.equal(flag.dataset.action,'unstar');
assert.equal(read.disabled,false);
assert.notEqual(readerStamp(before,true),readerStamp({...after,messages:[{...after.messages[0],reader_document:'different'}]},true));
console.log('Flag-only toolbar patch preserves document identity and rejects body changes.');
