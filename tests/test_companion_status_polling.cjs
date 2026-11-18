const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync('components/sports_cave_top_bar/index.html', 'utf8');
class Element {
  constructor() {this.children=[];this.dataset={};this.style={};this.events={};this.classList={toggle(){}};}
  focus() {this.focused=true;}
  append(...items) {for(const item of items){item.parent=this;this.children.push(item);}}
  replaceChildren(...items) {this.children=[];this.append(...items);}
  contains(item) {return item === this || this.children.some(child=>child.contains(item));}
  setAttribute(k,v) {this[k]=v;}
  removeAttribute(k) {delete this[k];}
  addEventListener(k,v) {this.events[k]=v;}
  remove() {this.parent.children=this.parent.children.filter(x=>x!==this);}
}
const nodes = new Map(), timers=[], storage=new Map();
const documentEvents = {}, windowEvents = {};
const state={config:{uploadScope:'admin',staffUploadProgress:true,navigationRouteLabels:{edition_ops:'Edition Ops'}}};
let payload={online:true,jobs:[]};
let queueResponse;
let disconnected=false, hold=false; const reads=[];
const writes=[];
const context={state, timers:new Set(), URLSearchParams, icon:name=>name,
 doc:{createElement:()=>new Element(),addEventListener:(event,callback)=>documentEvents[event]=callback},
 root:{querySelector:id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);},classList:{toggle(){}}},
 listenerController:new AbortController(), listenerOptions:{}, later:(fn,ms)=>{const timer={fn,ms};timers.push(timer);return timer;},
 parentWindow:{AbortController,
 setTimeout:(fn,ms)=>{const timer={fn,ms};timers.push(timer);return timer;},
 clearTimeout:timer=>{const i=timers.indexOf(timer);if(i>=0)timers.splice(i,1);},
 addEventListener:(event,callback)=>windowEvents[event]=callback,
 sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
 fetch:async(url,options)=>{
   if(disconnected)throw Error('offline');
   if (options?.method === 'POST') {
     const body=JSON.parse(options.body);
     writes.push({url,body});
     if(url.endsWith('/restart')) {
       payload.jobs[0]={...payload.jobs[0],stage:0,restartable:false,label:'Restart requested'};
       return {ok:true,json:async()=>({job:payload.jobs[0]})};
     }
     if (queueResponse) return queueResponse;
     payload.queues[body.queue].enabled=body.enabled;
     return {ok:true,json:async()=>({enabled:body.enabled})};
   }
   if(hold) return new Promise((resolve,reject)=>{
     reads.push({resolve,signal:options.signal});
     options.signal.addEventListener('abort',()=>reject(Object.assign(Error('timeout'),{name:'AbortError'})),{once:true});
   });
   reads.push({signal:options.signal});
   return {ok:true,json:async()=>payload};
 }}};
vm.createContext(context);
const install = () => vm.runInContext('{'+
 source.slice(source.indexOf('    const uploadNotices ='),source.indexOf('    const state ='))+
 '\nthis.show=showUploadNotice;this.refresh=refreshStaffProgress;}',context);
install();
(async()=>{
 const region=nodes.get('#sc-upload-notices');
 payload={online:true,jobs:[{id:'old-upload',stage:7,title:'Old failure',label:'Needs attention',detail:'Review retained'}],
   queues:{design:{enabled:true,jobs:[{id:'old-design',state:'failed',title:'Old design',label:'Needs attention',detail:'Retained detail'}]}}};
 await context.refresh();
 assert.equal(region.children.length,0,'initial historical snapshot is silent');
 assert.equal(timers.length,1);assert.equal(timers[0].ms,15000,'idle polling is slower');
 const row=nodes.get('#sc-os-design-list').children[0];
 await context.refresh();assert.equal(nodes.get('#sc-os-design-list').children[0],row);
 assert.equal(timers.length,1,'manual refresh replaces scheduled refresh');
 hold=true;
 const first=context.refresh(), second=context.refresh();
 assert.equal(reads.length,3,'overlapping polls share one request');
 reads.at(-1).resolve({ok:true,json:async()=>payload});
 await Promise.all([first,second]);assert.equal(timers.length,1);
 const hanging=context.refresh();
 const old=reads.at(-1);
 const afterAction=context.refresh(false);
 assert.equal(reads.at(-1),old,'action waits for previous read');
 old.resolve({ok:true,json:async()=>payload});
 await first;
 for(let i=0;i<10;i++)await Promise.resolve();
 assert.notEqual(reads.at(-1),old,'action requests a newer snapshot');
 reads.at(-1).resolve({ok:true,json:async()=>payload});
 await Promise.all([hanging,afterAction]);assert.equal(timers.length,1);
 const timed=context.refresh();
 timers.find(t=>t.ms===8000).fn();await timed;
 assert.equal(reads.at(-1).signal.aborted,true,'hung read aborts');
 assert.equal(nodes.get('#sc-os-design-status').dataset.stale,'true');
 assert.equal(timers.length,1);assert.equal(timers[0].ms,4000);
 hold=false;
 payload.queues.design.jobs[0].state='running';
 await context.refresh();
 assert.equal(nodes.get('#sc-os-design-status').dataset.stale,'false');
 assert.equal(timers[0].ms,2000,'active work polls faster');
 context.doc.hidden=true;const before=reads.length;
 await context.refresh();assert.equal(reads.length,before,'hidden tab does not fetch');
 assert.equal(timers[0].ms,30000);
 context.doc.hidden=false;documentEvents.visibilitychange();
 for(let i=0;i<10;i++)await Promise.resolve();
 assert.equal(reads.length,before+1,'visible tab refreshes immediately');
 hold=true;const obsolete=context.refresh();
 state.config.uploadScope='different-user';
 reads.at(-1).resolve({ok:true,json:async()=>({jobs:[{title:'Private old job'}]})});
 await obsolete;
 assert.notEqual(nodes.get('#sc-os-staff-upload-title').textContent,'Private old job');
 const destroyed=context.refresh();context.listenerController.abort();await destroyed;
 assert.equal(timers.length,0,'destroy aborts read and does not reschedule');
 console.log('Companion polling: silent history, retained DOM, single flight, fresh action reads, timeout recovery, adaptive cadence, visibility and teardown passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
