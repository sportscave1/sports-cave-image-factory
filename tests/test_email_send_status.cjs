const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {sendStatus,sentReceipt,locked}=require('../components/support_email/mail.js');
for(const copy of ['pending','unknown','appended']) {
  const model={draft:{id:'draft'},send_result:{status:'accepted'},sent_result:{status:copy}};
  assert.match(sendStatus(model),/✓ Sent<\/div>/);assert.equal(locked(model),true);
}
assert.equal(locked({draft:null,send_result:{status:'accepted'}}),false);
assert.match(sendStatus({send_result:{status:'accepted'},send_stage:'SAVING_SENT_COPY'}),/Saving Sent copy/);
assert.match(sentReceipt({last_sent:{operation_id:'op',copy:{status:'failed',retryable:true}}}),/Email sent successfully.*Retry saving Sent copy/);
assert.doesNotMatch(sentReceipt({last_sent:{operation_id:'op',copy:{status:'appended'}}}),/pending|Retry|Check/);
assert.match(sentReceipt({last_sent:{operation_id:'op',copy:{status:'unknown',retryable:false}}}),/Check Sent copy/);
assert.doesNotMatch(sentReceipt({last_sent:{operation_id:'op',copy:{status:'unknown',retryable:false}}}),/Retry/);
assert.match(sendStatus({send_result:{status:'unknown'}}),/⚠ Send status uncertain/);
assert.match(sendStatus({send_result:{status:'unknown'}}),/Do not resend yet/);
assert.match(sendStatus({send_result:{status:'rejected'}}),/✕ Not sent/);
const processing=sendStatus({send_result:{status:'in_progress'},send_progress:{percent:100}});
assert.doesNotMatch(processing,/✓ Sent|%|<progress/);assert.match(processing,/Validating email/);
assert.match(sendStatus({send_result:{status:'in_progress'},send_stage:'SENDING'}),/Sending email/);
const source=fs.readFileSync('components/support_email/mail.js','utf8');
assert.doesNotMatch(source,/percent:5|sc:send-progress|progress\.percent/);
const timers=[],ctx={model:{view:'mail',last_sent:{operation_id:'op',copy:{status:'pending'},checks:0}},busy:false,
  clearTimeout(){},setTimeout(fn,ms){timers.push({fn,ms});},emit(action,data){assert.equal(action,'auto_check_sent');assert.equal(data.operation_id,'op');}};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('let sentTimer='),source.indexOf("window.addEventListener('pagehide'",source.indexOf('let sentTimer=')))+';this.schedule=scheduleSentCheck;',ctx);
for(let n=0;n<5;n++){ctx.model.last_sent.checks=n;ctx.schedule();}
assert.deepEqual(timers.map(t=>t.ms),[6000,12000,24000]);timers[0].fn();
ctx.model.last_sent.checks=0;ctx.model.last_sent.copy.status='unknown';ctx.schedule();assert.equal(timers.length,3);
const stages=[],stageContext={model:{},busy:false,clearTimeout(){},setTimeout(fn){stages.push(fn);},emit(action,data){assert.equal(action,'advance_send');assert.equal(data.operation_id,'confirmed');}};
vm.createContext(stageContext);
vm.runInContext(source.slice(source.indexOf('let sendTimer='),source.indexOf("window.addEventListener('pagehide'",source.indexOf('let sendTimer=')))+';this.schedule=scheduleSendStage;',stageContext);
stageContext.schedule();assert.equal(stages.length,0); // Page load cannot send.
stageContext.model={send_stage:'SENDING',send_result:{operation_id:'confirmed',status:'in_progress'}};
stageContext.schedule();assert.equal(stages.length,1);stages[0]();
stageContext.model.send_stage='SAVING_SENT_COPY';stageContext.schedule();assert.equal(stages.length,2);
stageContext.model.send_stage='SENT';stageContext.schedule();assert.equal(stages.length,2);
console.log('Send status semantics and bounded polling checks passed.');
