const assert=require('node:assert/strict');
const {componentHandshake}=require('../components/support_email/mail.js');
function harness(){
 const timers=new Map();let id=0,calls=0,listener=false,received=0;
 const stop=componentHandshake((type,value)=>{
  assert.equal(type,'streamlit:componentReady');assert.equal(value.apiVersion,1);
  calls++;if(listener)received++;
 },(fn,ms)=>{assert.equal(ms,500);timers.set(++id,fn);return id;},key=>timers.delete(key));
 return {timers,stop,listen(){listener=true;},run(){const [key,fn]=timers.entries().next().value;timers.delete(key);fn();},get calls(){return calls;},get received(){return received;}};
}
const delayed=harness();assert.equal(delayed.calls,1);assert.equal(delayed.received,0);
delayed.listen();delayed.run();assert.equal(delayed.received,1);
delayed.stop();assert.equal(delayed.timers.size,0);assert.equal(delayed.calls,2);
const absent=harness();while(absent.timers.size)absent.run();assert.equal(absent.calls,20);
const hidden=harness();hidden.stop();assert.equal(hidden.timers.size,0);
console.log('Delayed host listener recovers; acknowledgement/page exit stops retries; absent host stops at 20 announcements.');
