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
const card=(id,top,parent)=>({classes:new Set(),dataset:{id,product:id,parent},getBoundingClientRect:()=>({top,bottom:top+100,height:100}),classList:{add(...names){names.forEach(n=>cards.find(c=>c.classList===this)?.classes.add(n));},remove(...names){names.forEach(n=>cards.find(c=>c.classList===this)?.classes.delete(n));}}});
const cards=[card('html-1',0),card('cat',100),card('html-2',200)];
const root={addEventListener:(name,fn)=>handlers[name]=fn,querySelectorAll:()=>cards,setPointerCapture(){},hasPointerCapture:()=>true,releasePointerCapture(){}};
const ctx=vm.createContext({drag:null,root,render(){},addEventListener:(name,fn)=>handlers[name]=fn,document:{querySelectorAll:()=>[]},reorder:(...args)=>reorders.push(args)});
vm.runInContext(source.slice(source.indexOf('function clearDrag'),source.indexOf("document.addEventListener('visibilitychange'")),ctx);
const handle={dataset:{drag:'cat',section:''},focus(){}};
const down=()=>handlers.pointerdown({target:{closest:()=>handle},button:0,clientX:10,clientY:110,pointerId:1,preventDefault(){}});
const move=y=>handlers.pointermove({clientX:10,clientY:y});
const up=()=>handlers.pointerup({pointerId:1});
down();move(5);assert.ok(cards[0].classes.has('drop-before'));assert.ok(cards[1].classes.has('drag-active'));up();assert.deepEqual(reorders.pop(),[null,'cat','html-1',false]);
down();move(299);up();assert.deepEqual(reorders.pop(),[null,'cat','html-2',true]);
down();up();assert.equal(reorders.length,0);
handlers.pointerdown({target:{closest:()=>null},button:0});move(10);up();assert.equal(reorders.length,0);
down();handlers.blur();assert.equal(vm.runInContext('drag',ctx),null);
down();handlers.pointercancel();assert.equal(vm.runInContext('drag',ctx),null);
console.log('Mouse before/after targets, handle-only initiation and cancellation passed');
const messages=[],listeners={};let sequence=0;
const parent={postMessage:msg=>messages.push(msg.value)};
const bridge=vm.createContext({parent,crypto:{randomUUID:()=>String(++sequence)},
 addEventListener:(name,fn)=>listeners[name]=fn,render(){}});
vm.runInContext("let historyScope,areas=new Map(),histories=new Map(),drag=null;let args={sections:[{id:'html-1',html:''}]},pending=false,inFlight=null,drafts={},queue=[],settingsDrafts={};"+
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

// Rapid presentation changes merge instead of losing unacknowledged toggles.
const updates=[];
const settingsContext=vm.createContext({settingsDrafts:{},emit:(type,event)=>updates.push(event)});
vm.runInContext(source.slice(source.indexOf('function changeSettings'),source.indexOf('function render')),settingsContext);
const section={id:'cat',settings:{columns:2,cta:'Claim Your Edition',display:{price:false,limit:true,remaining:true}}};
settingsContext.changeSettings(section,{display:{price:true}});
settingsContext.changeSettings(section,{display:{limit:false}});
settingsContext.changeSettings(section,{display:{remaining:false}});
assert.deepEqual(JSON.parse(JSON.stringify(updates[2].settings.display)),{price:true,limit:false,remaining:false});
console.log('Rapid catalogue settings retain all changes');

const timers=new Map(),ctaChanges=[];let timerId=0;
const input={setAttribute(){}};
const ctaContext=vm.createContext({parent:{dispatchEvent(){}},CustomEvent:class{},document:{createElement:()=>input},s:section,content:{append(){}},
 changeSettings:(s,patch)=>ctaChanges.push(patch),
 setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id)});
vm.runInContext(source.slice(source.indexOf('const cta='),source.indexOf('for(const warning')),ctaContext);
input.value='Claim Your Edition';input.oninput();assert.equal(ctaChanges.length,0);
input.onchange();assert.equal(timers.size,0);assert.equal(ctaChanges[0].cta,'Claim Your Edition');
input.value='';input.oninput();[...timers.values()][0]();assert.equal(ctaChanges.length,1);
console.log('CTA input debounce and blur commit checks passed');

// Metadata-only direct template menu: names are text, not injected HTML.
const menuNodes=[],templateEvents=[];const menu={open:true};
const menuContext=vm.createContext({args:{templates:[{id:'one',version:3,name:'<img onerror=alert(1)>'},{id:'two',version:1,name:'Trust Icons'}]},
 document:{getElementById:id=>id==='add'?menu:{replaceChildren:()=>menuNodes.splice(0),append:n=>menuNodes.push(n)}},
 el:tag=>({tag}),button:(text,label,fn)=>({text,label,fn,dataset:{}}),emit:(type,event)=>templateEvents.push({type,...event})});
vm.runInContext(source.slice(source.indexOf('function renderTemplates'),source.indexOf('function render(){')),menuContext);
menuContext.renderTemplates();assert.equal(menuNodes.length,3);
assert.equal(menuNodes[1].text,'<img onerror=alert(1)>');menuNodes[2].fn();
assert.equal(menu.open,false);assert.equal(templateEvents[0].template_id,'two');assert.equal(templateEvents[0].version,1);
menuContext.args.templates=[];menuContext.renderTemplates();assert.equal(menuNodes.length,0);
assert.ok(!fs.readFileSync('components/crm_sections/index.html','utf8').includes('Add Template'));
console.log('Direct template menu, safe labels, selected version, empty state checks passed');

// Queue captures local text even when a pending HTML acknowledgement precedes deletion.
bridge.drafts['html-1']='Latest not yet acknowledged';bridge.send('remove',{id:'html-1',confirmed:true});delete bridge.drafts['html-1'];
listeners.message({source:parent,data:{type:'streamlit:render',args:{sections:[{id:'html-1',html:'Older'}],ack:messages[3].event}}});
assert.equal(messages.at(-1).edits['html-1'],'Latest not yet acknowledged');
console.log('Queued structural action retains unacknowledged content');
