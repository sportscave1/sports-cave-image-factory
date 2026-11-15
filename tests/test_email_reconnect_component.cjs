const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {recoveryFeedback}=require('../components/support_email/mail.js');
const source=fs.readFileSync('components/support_email/mail.js','utf8');
assert.equal(recoveryFeedback({}), '');
assert.match(recoveryFeedback({},true), /reconnect-spinner.*Reconnecting mailbox/);
assert.match(recoveryFeedback({recovery:{state:'stopped',message:'Mailbox connection unavailable.'}}), /data-action="retry_connection".*Retry/);
assert.doesNotMatch(recoveryFeedback({recovery:{state:'waiting',message:'Reconnecting mailbox…'}}), /button/);
assert.match(recoveryFeedback({recovery:{state:'stopped',message:'<private>'}}), /&lt;private&gt;/);
let callback,delay,emitted=[];
const ctx={model:{recovery:{state:'waiting',delay_ms:15000}},busy:false,menu:null,document:{hidden:false},
  reconnectTimer:null,Math,clearTimeout(){callback=null;},setTimeout(fn,ms){callback=fn;delay=ms;return 1;},emit(action){emitted.push(action);}};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function scheduleReconnect('),source.indexOf("window.addEventListener('pagehide',()=>clearTimeout(reconnectTimer))"))+';this.schedule=scheduleReconnect;',ctx);
ctx.schedule();assert.equal(delay,15000);callback();assert.deepEqual(emitted,['reconnect']);
ctx.busy=true;callback();assert.equal(emitted.length,1);
ctx.busy=false;ctx.document.hidden=true;callback();assert.equal(emitted.length,1);
ctx.document.hidden=false;ctx.model.recovery.state='stopped';ctx.schedule();assert.equal(callback,null);
ctx.model.recovery.state='';ctx.schedule();assert.equal(callback,null);
let polls=0;
const live={model:{configured:true,recovery:{state:'stopped'}},pendingSignal:'',busy:false,menu:null,
  document:{hidden:false},Date:{now:()=>999999},lastLiveCheck:0,emit(){polls++;}};
vm.createContext(live);
vm.runInContext(source.slice(source.indexOf('function liveTick('),source.indexOf('// Only standalone'))+';this.tick=liveTick;',live);
live.tick();assert.equal(polls,0);
live.model.recovery.state='waiting';live.tick();assert.equal(polls,0);
live.model.recovery.state='';live.tick();assert.equal(polls,1);
console.log('Reconnect component: feedback, bounded timer ownership, stopped/manual Retry and healthy heartbeat passed.');
