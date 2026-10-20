const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('task_recorder/panel.js','utf8'),elements=new Map();
let issue={kind:'prerequisite',step:2,explanation:'Choose the source first'};
const c={state:{mode:'running',message:'Step 2 of 8 — upload: Choose PSD',protocol:4},
 device:{connected:true,state:{}},transportOK:true,pending:new Map(),selected:'a',attentionKey:'',
 online:()=>true,starting:()=>false,active:()=>false,
 tasks:()=>[{id:'a',revision:'r',attention:[issue]}],
 $:id=>{if(!elements.has(id))elements.set(id,{});return elements.get(id)}};
vm.createContext(c);
vm.runInContext(source.slice(source.indexOf('function status(){'),source.indexOf('function renderControls(){')),c);
vm.runInContext(source.slice(source.indexOf('function renderAttention(){'),source.indexOf("$('correctionKind').onchange=")),c);
assert.equal(c.status(),'Step 2 of 8 — upload: Choose PSD');
c.renderAttention();assert.equal(elements.get('repairCopy').disabled,true);
assert.equal(elements.get('attentionReason').textContent,'Choose the source first');
issue={kind:'target',step:3,explanation:'Rerecord the named control'};
c.renderAttention();assert.equal(elements.get('repairCopy').disabled,true);
issue={kind:'unsupported',step:2,explanation:'Old passive frame flag'};
c.renderAttention();assert.equal(elements.get('repairCopy').disabled,false);
console.log('PASS exact progress and no misleading wait correction for missing source/target');
