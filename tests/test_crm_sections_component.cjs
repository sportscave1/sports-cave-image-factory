const assert=require('node:assert/strict');
const {moveId}=require('../components/crm_sections/composer.js');
assert.deepEqual(moveId(['html-1','catalogue','html-2'],'catalogue','html-1'),['catalogue','html-1','html-2']);
assert.deepEqual(moveId(['1','2','3'],'1','3'),['2','3','1']);
assert.deepEqual(moveId(['1','2'],'missing','1'),['1','2']);
const original=['1','2'];moveId(original,'2','1');assert.deepEqual(original,['1','2']);
// Exercise the actual pointer and keyboard handlers with a minimal event target.
const vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('components/crm_sections/composer.js','utf8');
const handlers={},reorders=[];
let target=null;
const ctx=vm.createContext({drag:null,document:{addEventListener:(name,fn)=>handlers[name]=fn,
 querySelectorAll:()=>[],elementFromPoint:()=>target},reorder:(...args)=>reorders.push(args)});
vm.runInContext(source.slice(source.indexOf("document.addEventListener('pointerdown'"),source.indexOf("addEventListener('message'")),ctx);
const handle={dataset:{drag:'cat',section:''},setPointerCapture(){}};
const down=()=>handlers.pointerdown({target:{closest:()=>handle},clientX:10,clientY:10,pointerId:1});
const move=()=>handlers.pointermove({clientX:10,clientY:60});
const up=()=>handlers.pointerup({clientX:10,clientY:60});
down();target={closest:()=>({dataset:{id:'html-1'},classList:{add(){}}})};move();up();
assert.deepEqual(reorders.pop(),[null,'cat','html-1']);
// Header/footer are outside the middle component and cannot be drop targets.
down();target=null;move();up();assert.equal(reorders.length,0);
handle.dataset.section='cat';handle.dataset.drag='p2';down();
target={closest:()=>({dataset:{parent:'cat',product:'p1'},classList:{add(){}}})};move();up();
assert.deepEqual(reorders.pop(),['cat','p2','p1']);
down();target={closest:()=>({dataset:{parent:'another-cat',product:'p1'},classList:{add(){}}})};move();up();
assert.equal(reorders.length,0);
// A handle click without a drag must not reorder.
down();up();assert.equal(reorders.length,0);
console.log('9 section/product ordering and pointer boundary checks passed');
const messages=[],listeners={};let sequence=0;
const parent={postMessage:msg=>messages.push(msg.value)};
const bridge=vm.createContext({parent,crypto:{randomUUID:()=>String(++sequence)},
 addEventListener:(name,fn)=>listeners[name]=fn,render(){}});
vm.runInContext("let args={sections:[{id:'html-1',html:''}]},pending=false,inFlight=null,drafts={},queue=[];"+
 source.slice(source.indexOf('const emit='),source.indexOf('const el='))+
 source.slice(source.indexOf("addEventListener('message'"),source.indexOf('new ResizeObserver'))+
 ';this.send=emit;this.drafts=drafts;',bridge);
bridge.send('order',{ids:['html-1']});bridge.send('visible',{id:'html-1',visible:false});
assert.equal(messages.length,1);
listeners.message({source:parent,data:{type:'streamlit:render',args:{sections:[{id:'html-1',html:''}],ack:messages[0].event}}});
assert.equal(messages.length,2);assert.equal(messages[1].type,'visible');
bridge.drafts['html-1']='<p>Typing during a pending action</p>';
listeners.message({source:parent,data:{type:'streamlit:render',args:{sections:[{id:'html-1',html:''}],ack:messages[1].event}}});
assert.equal(messages[2].html,'<p>Typing during a pending action</p>');
listeners.message({source:parent,data:{type:'streamlit:render',args:{sections:[{id:'html-1',html:messages[2].html}],ack:messages[2].event}}});
bridge.send('picker',{id:'cat'});assert.equal(messages[3].type,'picker');
console.log('4 acknowledgement, queued action and pending-edit checks passed');
