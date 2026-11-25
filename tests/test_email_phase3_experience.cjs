const assert=require('node:assert/strict');
const {connectionPresentation:present,listNavigationIndex:nav,loadingPlaceholder}=require('../components/support_email/mail.js');
const connected={configured:true,threads:[{}],sync_health:{state:'CONNECTED'},recovery:{}};
assert.equal(present(connected).state,'connected');
assert.equal(present({...connected,configured:false}).state,'offline');
// A queued read is ordinary syncing, including the workspace's waiting state.
assert.equal(present({...connected,read_pending:true,recovery:{state:'waiting',delay_ms:1000}}).state,'syncing');
const reconnect=present({...connected,sync_health:{state:'RECONNECTING',retry_after:8},recovery:{state:'waiting',delay_ms:4000}});
assert.equal(reconnect.state,'reconnecting');assert.equal(reconnect.retry_ms,8000);
assert.match(reconnect.detail,/last synced mail/);
for(const category of ['authentication','configuration','tls']){
  const result=present({...connected,sync_health:{state:'RECONNECTING',category,retry_after:90}});
  assert.equal(result.state,'attention');assert.equal(result.retry_ms,0);
}
assert.equal(present({...connected,recovery:{state:'stopped'}}).state,'attention');
assert.equal(present({...connected,error:'network',recovery:{delay_ms:Infinity}}).retry_ms,0);
assert.equal(present({...connected,error:'network',recovery:{delay_ms:9e9}}).retry_ms,900000);
// Selection keys stay inside the list; unrelated keys have no navigation result.
assert.equal(nav('Home',3,5),0);assert.equal(nav('End',1,5),4);
assert.equal(nav('ArrowUp',0,5),0);assert.equal(nav('ArrowDown',4,5),4);
for(const key of ['Enter','Delete','r','f',' '])assert.equal(nav(key,2,5),-1);
assert.equal(nav('ArrowDown',0,0),-1);
assert.match(loadingPlaceholder(),/role="status"/);assert.match(loadingPlaceholder(),/aria-hidden="true"/);
console.log('Connection states, ordinary sync, bounded retry display and keyboard boundaries passed.');
// Exercise production focus restoration across replacement of the loading heading.
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('components/support_email/mail.js','utf8');
const body={},oldHeading={isConnected:false},heading={disabled:false,getClientRects:()=>[{}],
  focus(){if(this.tabIndex===-1)doc.activeElement=this;}};
const doc={activeElement:body,body,hasFocus:()=>true};
const context={document:doc,root:{querySelector:()=>heading}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function restoreUIFocus('),source.indexOf('function returnToList('))+';this.restore=restoreUIFocus;',context);
context.restore({node:oldHeading,reader:true});
assert.equal(doc.activeElement,heading,'The replacement heading must be focusable before restoring focus');
const other={};doc.activeElement=other;context.restore({node:oldHeading,reader:true});
assert.equal(doc.activeElement,other,'A refresh must not steal focus from another control');
doc.activeElement=body;doc.hasFocus=()=>false;context.restore({node:oldHeading,reader:true});
assert.equal(doc.activeElement,body,'An inactive inbox must not claim keyboard focus');
console.log('Reader focus survives loading replacement and respects focus held elsewhere.');
