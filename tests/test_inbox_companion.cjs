'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const pageSource=fs.readFileSync(require.resolve('../windows-upload-companion/inbox-page.js'),'utf8');
const queueSource=fs.readFileSync(require.resolve('../windows-upload-companion/inbox-queue.js'),'utf8');
const old={name:'Fixture Customer',email:'fixture@example.test',phoneNumber:'+61000000000',address:{line1:'1 Old Street',line2:'Unit 1',townOrCity:'Sydney',stateOrCounty:'NSW',postalOrZipCode:'2000',countryCode:'AU'}};
const updated={...old,address:{...old.address,line1:'2 New Street',line2:'',postalOrZipCode:'2001'}};
const base={key:'inbox_companion_request:'+'a'.repeat(64),token:'a'.repeat(43),order_id:'99',reference:'123',order_url:'https://dashboard.prodigi.com/orders/99/detail',action:'address',recipient:updated,before_recipient:old};
const node=text=>({textContent:text,isConnected:true,disabled:false,getClientRects:()=>[{}]});

function page(options={}){
 let listener,opened=false,held=options.held||false,saves=0,cancels=0,pauses=0,permits=0,events=0;
 class Input{constructor(value){this._value=value;this.isConnected=true;this.disabled=false;}get value(){return this._value;}set value(v){this._value=v;}getClientRects(){return [{}]}dispatchEvent(){events++;}}
 const fields={};for(const [key,id] of Object.entries(require('../windows-upload-companion/inbox-page.js').inboxAddressFields))fields[id]=new Input(key==='name'?old.name:old.address[key]||'');
 if(options.changedAddress)fields['recipient-address-line-1-field'].value='Someone else changed it';
 const edit={...node('Edit address'),click(){opened=true;}},save={...node('Save and close'),click(){saves++;if(!options.saveUncertain)opened=false;}},cancel={...node('Cancel changes'),click(){cancels++;opened=false;}},pause={...node('Pause indefinitely'),click(){pauses++;held=true;}};
 const main={...node('Order reference 123'),querySelectorAll(selector){if(selector==='button')return options.production||held?[edit]:[edit,pause];return[];}};
 const modal={...node('Edit address'),querySelector(selector){if(selector==='#recipient_country_field')return {value:options.country||'Australia',disabled:true};throw Error('Unexpected '+selector);},
  querySelectorAll(selector){if(selector==='h1,h2')return[node('Edit address')];if(selector==='button')return[save,cancel];const id=selector.match(/^\[id="(.+)"\]$/)?.[1];if(id)return fields[id]?[fields[id]]:[];throw Error('Unexpected '+selector);}};
 const context={document:{querySelector:()=>main,querySelectorAll(selector){if(selector==='main h1')return[node(options.wrongHeading?'990':'99 Copy to clipboard')];if(selector==='[role="dialog"]')return opened?[modal]:[];throw Error('Unexpected '+selector);}},
  location:{href:options.wrongUrl?'https://dashboard.prodigi.com/orders/other/detail':base.order_url},HTMLInputElement:Input,Event:class{},
  prodigiIndefiniteHold:()=>held,prodigiObserveReady:async fn=>{for(let i=0;i<4;i++){const result=fn();if(result)return result;}throw Error('Timed out');},
  chrome:{runtime:{id:'paired',onMessage:{addListener:fn=>listener=fn},sendMessage:async message=>{assert.equal(message.type,'inbox:permit');permits++;return {permitted:!options.denied,order_id:'99',action:options.action||'address'};}}}};
 vm.runInNewContext(pageSource,context);
 return {run:async(plan=base)=>new Promise(resolve=>listener({type:'inbox:run',plan},{id:'paired'},resolve)),get state(){return {saves,cancels,pauses,permits,events,opened,held}},fields};
}
test('address editor changes only complete address fields and saves once after permission',async()=>{
 const p=page();const result=await p.run();assert.equal(result.evidence.address_saved,true);
 assert.equal(p.state.saves,1);assert.equal(p.state.pauses,0);assert.equal(p.state.permits,1);
 assert.equal(p.fields['recipient-address-line-2-field'].value,'');
});
for(const [name,options] of Object.entries({denied:{denied:true},wrongUrl:{wrongUrl:true},wrongHeading:{wrongHeading:true},production:{production:true},country:{country:'United States'},changedAddress:{changedAddress:true}}))test('no Save for '+name,async()=>{
 const p=page(options);assert((await p.run()).error);assert.equal(p.state.saves,0);assert.equal(p.state.pauses,0);
});
test('uncertain save is never clicked twice and is returned for server review',async()=>{
 const p=page({saveUncertain:true});assert((await p.run()).error);assert.equal(p.state.saves,1);assert.equal(p.state.cancels,1);
});
for(const initial of [false,true])test('customer order changes pause indefinitely once, retaining an existing indefinite pause '+initial,async()=>{
 const p=page({held:initial,action:'hold'});const result=await p.run({...base,action:'hold',recipient:null});
 assert.equal(result.evidence.indefinite_hold,true);assert.equal(p.state.saves,0);assert.equal(p.state.pauses,initial?0:1);
});

function worker(overrides={}){
 let alarms=[],calls=[],removed=[],tabCalls=0,listener,wakes=0;
 const storage={staffQueueCredential:'paired',...(overrides.pending?{inboxBrowserPending:base}:{})};
 const context={URL,AbortSignal,setInterval:()=>1,clearInterval:()=>{},ordersTickRunning:!!overrides.ordersBusy,osOrigin:'https://sports-cave-image-factory.onrender.com',
  prodigiWorkerTab:async()=>{tabCalls++;return {id:17}},prodigiWaitForPage:async()=>true,
  fetch:async(url,options)=>{const action=url.split('/').pop();calls.push({action,body:JSON.parse(options.body)});if(overrides.failure)throw Error('Offline');return {ok:true,json:async()=>action==='tick'?(overrides.empty?{}:{browser:overrides.plan||base}):{permitted:true}};},
  continueOrdersSoon:()=>{assert.equal(context.ordersTickRunning,false);wakes++;},
  chrome:{storage:{local:{get:async key=>typeof key==='string'?{[key]:storage[key]}:storage,set:async value=>Object.assign(storage,value),remove:async key=>{removed.push(key);delete storage[key]}}},
   alarms:{get:async()=>null,create:async(name)=>alarms.push(name),onAlarm:{addListener:()=>{}}},runtime:{id:'paired',onStartup:{addListener:()=>{}},onInstalled:{addListener:()=>{}},onMessage:{addListener:fn=>listener=fn}},
   tabs:{sendMessage:async()=>({evidence:{address_saved:true}})}}};
 vm.runInNewContext(queueSource,context);return{context,calls,storage,removed,get tabCalls(){return tabCalls},get wakes(){return wakes},listener};
}
test('Inbox scans during an Orders upload without touching its tab or releasing its writer',async()=>{
 const w=worker({ordersBusy:true});assert.equal(await w.context.inboxQueueTick(),true);assert.deepEqual(w.calls.map(c=>c.action),['tick']);assert.equal(w.tabCalls,0);assert.equal(w.context.ordersTickRunning,true);
 assert.equal(w.wakes,0);
});

for(const options of [{empty:true},{failure:true},{}])test('coalesced alarms always wake Orders after Inbox yields '+JSON.stringify(options),async()=>{
 const w=worker(options);const pending=w.context.inboxQueueTick();
 assert.equal(w.context.ordersTickRunning,true); // An Orders alarm at this instant must yield.
 await pending;
 assert.equal(w.context.ordersTickRunning,false);assert.equal(w.wakes,1);
});
test('Inbox uses the existing paired server and owned tab, then finishes once',async()=>{
 const w=worker();assert.equal(await w.context.inboxQueueTick(),true);assert.deepEqual(w.calls.map(c=>c.action),['tick','finish']);assert.equal(w.tabCalls,1);assert.equal(w.context.ordersTickRunning,false);
 assert.equal(w.storage.inboxBrowserPending,undefined);
});
test('interrupted browser action goes to readback before any new handoff',async()=>{
 const w=worker({pending:true});await w.context.inboxQueueTick();assert.equal(w.calls[0].action,'finish');assert(w.calls[0].body.error.includes('Interrupted'));
});
for(const mutation of [p=>p.order_url='https://evil.test/',p=>p.action='cancel',p=>p.recipient.address.countryCode='US',p=>p.recipient.address.line1=''])test('invalid server handoff never opens a tab',async()=>{
 const plan=JSON.parse(JSON.stringify(base));mutation(plan);const w=worker({plan});assert.equal(await w.context.inboxQueueTick(),false);assert.equal(w.tabCalls,0);
});
test('a different tab cannot use the active Inbox write permit',async()=>{
 const w=worker();w.context.inboxActive={plan:base,tab:17};let replied=false;
 const result=w.listener({type:'inbox:permit'},{id:'paired',tab:{id:18}},()=>{replied=true});
 assert.equal(result,undefined);assert.equal(replied,false);assert.equal(w.calls.length,0);
});
