const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('task_recorder/panel.js','utf8');
const send=source.slice(source.indexOf('async function send(kind,'),source.indexOf('async function reconcile()'));
function setup(){
 let ids=0,calls=0;
 const c={device:{id:'pc',state:{}},stepEditor:{},stopped:false,pending:new Map(),rowErrors:new Map(),
  online:()=>true,modern:()=>true,starting:()=>false,active:()=>false,uuid:()=>String(++ids),
  remember(){},error(){},notice(){},render(){},confirmCommand:async()=>({new_task_id:'copy'}),
  api:async()=>{calls++;return {status:'applied'};}};
 vm.createContext(c);vm.runInContext(send,c);return c;
}
(async()=>{
 const c=setup();let first=true;
 c.api=async()=>{if(first){first=false;const error=Error('Invalid step');error.rejected=true;throw error;}return {status:'applied'};};
 assert.equal(await c.send('edit-copy',{id:'source'}),null);assert.equal(c.pending.size,0);
 assert.equal((await c.send('edit-copy',{id:'source'})).new_task_id,'copy');assert.equal(c.pending.size,0);
 // Ambiguous network outcomes retain their command identity and block new Save.
 const offline=setup();let calls=0;offline.api=async()=>{calls++;throw Error('Connection lost');};
 assert.equal(await offline.send('edit-copy',{id:'source'}),null);assert.equal(offline.pending.size,1);
 const before=calls;assert.equal(await offline.send('edit-copy',{id:'source'}),null);assert.equal(calls,before);
 // A receipt read failure after dispatch is not proof that Save was rejected.
 const receipt=setup();receipt.confirmCommand=async()=>{const e=Error('Sign in');e.rejected=true;throw e;};
 let sent=false;receipt.api=async()=>{if(!sent){sent=true;return {status:'queued'};}throw Error('Receipt unavailable');};
 assert.equal(await receipt.send('edit-copy',{id:'source'}),null);assert.equal(receipt.pending.size,1);
 // Normal starts cannot compete with an open editor; Stop remains available.
 assert.equal(await c.send('play',{id:'source'}),null);
 assert.equal(await c.send('record',{}),null);
 assert.equal((await c.send('stop',{})).new_task_id,'copy');
 console.log('PASS rejected Save retry, uncertain Save identity retained, no duplicate Save, editor start guards, Stop available');
})().catch(e=>{console.error(e);process.exitCode=1;});
