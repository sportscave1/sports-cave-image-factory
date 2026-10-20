const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('task_recorder/panel.js','utf8');
const fn=source.slice(source.indexOf('function renderControls(){'),source.indexOf('\nfunction date('));
const elements=new Map();
const context={stepEditor:null,editorLoading:false,state:{mode:'completed',active_task_name:'Previous completed task'},selected:'selected',device:{},pending:new Map([['command',{kind:'play',payload:{id:'requested'}}]]),
 $:id=>{if(!elements.has(id))elements.set(id,{});return elements.get(id);},
 tasks:()=>[{id:'requested',name:'Requested recording'},{id:'selected',name:'Other selected recording'}],
 activeModes:new Set(['recording','recording_paused','running','pausing','paused','starting']),
 active:()=>context.activeModes.has(context.state.mode),starting:()=>context.pending.size>0,
 online:()=>true,modern:()=>true,status:()=>''};
vm.createContext(context);vm.runInContext(fn,context);context.renderControls();
assert.equal(elements.get('activeName').textContent,'Requested recording');
context.pending.clear();context.state={mode:'running',active_task_name:'Actual active recording'};context.renderControls();
assert.equal(elements.get('activeName').textContent,'Actual active recording');
assert.equal(elements.get('pause').hidden,false);assert.equal(elements.get('stop').hidden,false);
context.state={mode:'paused',can_resume:true,active_task_name:'Actual active recording'};context.renderControls();
assert.equal(elements.get('resume').hidden,false);assert.equal(elements.get('activeName').textContent,'Actual active recording');
context.state={mode:'idle'};context.stepEditor={};context.renderControls();
assert.equal(elements.get('record').disabled,true);assert.equal(elements.get('play').disabled,true);
console.log('PASS requested start name, active run independent of selection, acknowledged Pause/Resume controls');
