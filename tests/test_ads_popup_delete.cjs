const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync('components/sports_cave_top_bar/index.html', 'utf8');
class Element {
  constructor() {this.children=[];this.dataset={};this.style={};this.events={};this.classList={toggle(){}};}
  focus() {this.focused=true;}
  append(...items) {for(const item of items){item.parent=this;this.children.push(item);}}
  insertBefore(item,before) {if(item.parent)item.remove();const i=before?this.children.indexOf(before):this.children.length;item.parent=this;this.children.splice(i,0,item);}
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
let queueResponse, resolveAction;
let disconnected=false, hold=false; const reads=[];
const writes=[];
const context={state, timers:new Set(), URLSearchParams, icon:name=>name,
 doc:{createElement:()=>new Element(),addEventListener:(event,callback)=>documentEvents[event]=callback},
 root:{querySelector:id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);},classList:{toggle(){}}},
 listenerController:new AbortController(), listenerOptions:{}, later:(fn,ms)=>{const timer={fn,ms};timers.push(timer);return timer;},
 parentWindow:{AbortController,
 // Summary rotation is covered by browser tests; this fixture exercises polling timers only.
 setInterval:()=>1,
 setTimeout:(fn,ms)=>{const timer={fn,ms};timers.push(timer);return timer;},
 clearTimeout:timer=>{const i=timers.indexOf(timer);if(i>=0)timers.splice(i,1);},
 addEventListener:(event,callback)=>windowEvents[event]=callback,
 sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
 fetch:async(url,options)=>{
   if(disconnected)throw Error('offline');
   if (options?.method === 'POST') {
     const body=JSON.parse(options.body);
     writes.push({url,body});
     if(url.endsWith('/ad-control'))return new Promise(resolve=>{resolveAction=resolve;});
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
 const one={id:'one',title:'Same title',state:'waiting',label:'Queued',can_play:true,can_cancel:true};
 const two={...one,id:'two'};
 payload={online:true,jobs:[],queues:{ads:{enabled:true,online:true,waiting:2,jobs:[one,two]}}};
 await context.refresh();
 const list=nodes.get('#sc-os-ads-list');
 const first=list.children[0];
 one.updated_at='new timestamp';payload.checked_at='new timestamp';await context.refresh();
 assert.equal(list.children[0],first,'timestamp refresh must not replace pressed controls');
 const deleting=first.children[0].children[2].onclick();
 assert.equal(list.children.length,2,'clicked row disappears before POST resolves; other row and link remain');
 assert.match(nodes.get('#sc-os-queue-ads').innerHTML,/Ads \(1\)/);
 await context.refresh();
 assert.equal(list.children.length,2,'stale read cannot resurrect pending delete');
 resolveAction({ok:true,json:async()=>({id:'one',action:'delete'})});
 await deleting;
 assert.equal(writes.length,1);
 assert.equal(list.children.length,2,'successful delete stays hidden even with cached response');
 assert.equal(nodes.get('#sc-os-ads-title').dataset.jobId,'two','summary advances to remaining duplicate-title job');
 const failing=list.children[0].children[0].children[2].onclick();
 assert.equal(list.children.length,1,'second delete is also immediate');
 resolveAction({ok:false,json:async()=>({error:'Delete rejected'})});
 await failing;
 assert.equal(list.children.length,2,'failed delete restores only rejected job');
 assert.equal(nodes.get('#sc-upload-notices').children.length,0,'Ads errors stay inline and cannot cover retry controls');
 assert.equal(nodes.get('#sc-ad-message').textContent,'Delete rejected');
 state.config.uploadScope='new-account';payload.checked_at='next';await context.refresh();
 assert.equal(list.children.length,3,'local deletions cannot leak across account scopes');
 console.log('Ads delete: immediate removal, stale-read suppression, duplicate-title identity, failure rollback, stable buttons and scope isolation passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
