const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {sendStatus,locked}=require('../components/support_email/mail.js');
for(const copy of ['pending','unknown','appended']) {
  const model={send_result:{status:'accepted'},sent_result:{status:copy}};
  assert.match(sendStatus(model),/✓ Sent<\/div>/);assert.match(sendStatus(model),/● Sent copy pending/);assert.equal(locked(model),true);
}
assert.match(sendStatus({send_result:{status:'accepted'},sent_result:{status:'present'}}),/✓ Sent copy available/);
assert.match(sendStatus({send_result:{status:'unknown'}}),/⚠ Send status uncertain/);
assert.match(sendStatus({send_result:{status:'unknown'}}),/Do not resend yet/);
assert.match(sendStatus({send_result:{status:'rejected'}}),/✕ Not sent/);
const processing=sendStatus({send_result:{status:'in_progress'},send_progress:{percent:100}});
assert.doesNotMatch(processing,/✓ Sent|100%/);assert.match(processing,/<progress/);
const source=fs.readFileSync('components/support_email/mail.js','utf8');
const timers=[],ctx={model:{view:'compose',send_result:{status:'accepted'},sent_result:{status:'pending'},sent_checks:0,draft:{operation_id:'op'}},busy:false,
  clearTimeout(){},setTimeout(fn,ms){timers.push({fn,ms});},emit(action,data){assert.equal(action,'auto_check_sent');assert.equal(data.operation_id,'op');}};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('let sentTimer='),source.indexOf("window.addEventListener('pagehide'",source.indexOf('let sentTimer=')))+';this.schedule=scheduleSentCheck;',ctx);
for(let n=0;n<5;n++){ctx.model.sent_checks=n;ctx.schedule();}
assert.deepEqual(timers.map(t=>t.ms),[6000,12000,24000]);timers[0].fn();
ctx.model.sent_checks=0;ctx.model.send_result.status='unknown';ctx.schedule();assert.equal(timers.length,3);
console.log('Send status semantics and bounded polling checks passed.');
