const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('components/campaign_recovery/test_flush.js','utf8');
function fixture(){
 const handlers={},calls=[];let release;
 const barrier=new Promise(resolve=>release=resolve);
 const status={dataset:{},setAttribute(){}};
 const input={id:'recipient',value:'fixture@example.test',closest:()=>form};
 const form={isConnected:true,querySelector:s=>s.includes('input')?input:s.includes('button')?button:status};
 const button={isConnected:true,click:()=>calls.push('submit')};
 const window={scCampaignFlushSections:()=>{calls.push('sections');return barrier;},scCampaignFlushRecovery:async()=>calls.push('recovery')};
 const document={getElementById:()=>input,activeElement:{blur:()=>calls.push('blur')},addEventListener:(name,fn)=>handlers[name]=fn};
 vm.runInNewContext(source,{window,document});
 const event=(type='click')=>({type,key:'Enter',target:{closest:s=>s.includes('stForm')?form:button},preventDefault(){calls.push('prevent');},stopImmediatePropagation(){calls.push('stop');}});
 return {handlers,calls,release,window,status,event};
}
test('click waits for section acknowledgement then recovery before submit',async()=>{
 const f=fixture(),pending=f.handlers.click(f.event());assert.ok(!f.calls.includes('submit'));
 await f.handlers.click(f.event());f.release();await pending;
 assert.deepEqual(f.calls.slice(-2),['recovery','submit']);assert.equal(f.calls.filter(v=>v==='submit').length,1);
});
test('Enter follows same barrier and failed recovery never submits',async()=>{
 const f=fixture();f.window.scCampaignFlushRecovery=async()=>{throw Error('conflict');};
 const pending=f.handlers.keydown(f.event('keydown'));f.release();await pending;
 assert.ok(!f.calls.includes('submit'));assert.match(f.status.textContent,/no test was sent/);
});
