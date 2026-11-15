const assert=require('node:assert/strict');
const {recipients,valid,sizes,snippets,filterRows}=require('../components/support_email/mail_tools.js');
assert.equal(recipients('"Last, First" <person@example.test>, other@example.test').length,2);
assert.equal(recipients('"Last, First" <person@example.test>')[0].email,'person@example.test');
for(const value of ['x\n@example.test','broken','a@b','<x@example.test>'])assert.equal(valid(value),false);
assert.equal(valid('customer+reply@example.test'),true);
assert.deepEqual(sizes({folder:'bad',list:99999},1024),{folder:176,list:520});
assert.deepEqual(sizes({folder:-100,list:0},1440),{folder:140,list:260});
assert.equal(snippets.length,6);assert(snippets.every(([title,text])=>title&&text&&!text.includes('<')));
const rows=[{unread:true,starred:false,attachment:true,date:'2026-10-11',subject:'Delivery',email:'a@example.test',recipients:'b@example.test'},
 {unread:false,starred:true,attachment:false,date:'2026-10-10',subject:'Order',email:'c@example.test'}];
assert.equal(filterRows(rows,{unread:true,attachments:true,since:'2026-10-11',sender:'a@',recipient:'b@',subject:'del'}).length,1);
assert.equal(filterRows(rows,{unread:true,flagged:true}).length,0);
assert.equal(filterRows(rows,{before:'2026-10-11'}).length,1);
console.log('V2D recipient parsing, validation, pane bounds, neutral reply catalog and combined cached filters passed.');
