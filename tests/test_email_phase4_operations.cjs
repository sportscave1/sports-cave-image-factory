const assert=require('node:assert/strict');
const {createSelectionSummary,operationsFeedback,readerStamp}=require('../components/support_email/mail.js');
const metrics=createSelectionSummary();
for(let i=0;i<500;i++)metrics.observe({source:'cold',stage:'body',duration_ms:i,message_id:'must not survive'});
for(const duration_ms of [NaN,Infinity,-1,'secret'])metrics.observe({source:'cold',stage:'header',duration_ms});
metrics.observe({source:'customer@example.test',stage:'body',duration_ms:1});
const result=metrics.snapshot();
assert.deepEqual(result.cold_body,{count:200,p50_ms:399,p95_ms:489});
assert.equal(result.cold_header.count,0);assert.equal(Object.keys(result).length,4);
assert.doesNotMatch(JSON.stringify(result),/secret|message_id|customer/);
assert.match(operationsFeedback({state:'needs_attention',last_successful_poll_age_seconds:130,
  alerts:[{message:'<script>unsafe</script>'}]}),/Email operations need attention/);
assert.doesNotMatch(operationsFeedback({alerts:[{message:'<script>unsafe</script>'}]}),/<script>/);
assert.match(operationsFeedback({state:'off'}),/automation is off/);
console.log('Bounded anonymous click timings, aggregate quantiles and escaped operational feedback passed.');

assert.notEqual(readerStamp({view:'settings'}),readerStamp({view:'settings',admin_operations:{state:'healthy'}}),'Diagnostics must repaint after the reply arrives');
assert.equal(readerStamp({view:'mail'}),readerStamp({view:'mail',admin_operations:{state:'healthy'}}),'Diagnostics must not repaint an open customer message');
