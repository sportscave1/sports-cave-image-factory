const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('components/support_email/mail.js','utf8');
const timers=new Map(),handlers={},events=[];let id=0;
const ctx={model:{durable_drafts:true,draft:{id:'draft'}},busy:false,locked:()=>false,$:()=>null,
 root:{addEventListener(name,fn){handlers[name]=fn;}},window:{addEventListener(){}},
 clearTimeout(key){timers.delete(key);},setTimeout(fn,ms){assert.equal(ms,1500);timers.set(++id,fn);return id;},
 emit(action){events.push(action);}};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('let autosaveTimer='),source.indexOf('let sentTimer=')),ctx);
const input={target:{id:'editor',closest:()=>null}};
for(let n=0;n<20;n++)handlers.input(input);
assert.equal(timers.size,1);assert.equal(events.length,0);
const fire=()=>{const [key,fn]=[...timers.entries()][0];timers.delete(key);fn();};
fire();assert.deepEqual(events,['autosave_draft']);
ctx.busy=true;handlers.input(input);fire();assert.equal(events.length,1);
assert.equal(timers.size,1);ctx.busy=false;fire();assert.equal(events.length,2);
ctx.model.durable_drafts=false;timers.clear();handlers.input(input);assert.equal(timers.size,0);
assert.match(source,/liveUpdate&&model.view==='compose'/);
assert.match(source,/liveUpdate=.*autosave_draft/);
console.log('Draft autosave debounce, busy retry and composer preservation guards passed.');
