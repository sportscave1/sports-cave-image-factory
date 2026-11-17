const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const source = fs.readFileSync('components/sports_cave_top_bar/index.html', 'utf8');
class Element {
  constructor() {this.children=[];this.dataset={};this.style={};this.events={};this.classList={toggle(){}};}
  focus() {this.focused=true;}
  append(...items) {for(const item of items){item.parent=this;this.children.push(item);}}
  replaceChildren(...items) {this.children=[];this.append(...items);}
  setAttribute(k,v) {this[k]=v;}
  removeAttribute(k) {delete this[k];}
  addEventListener(k,v) {this.events[k]=v;}
  remove() {this.parent.children=this.parent.children.filter(x=>x!==this);}
}
const nodes = new Map(), timers=[], storage=new Map();
const state={config:{uploadScope:'admin',staffUploadProgress:true,navigationRouteLabels:{edition_ops:'Edition Ops'}}};
let payload={online:true,jobs:[]};
const writes=[];
const context={state, URLSearchParams, icon:name=>name, doc:{createElement:()=>new Element()},
 root:{querySelector:id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);},classList:{toggle(){}}},
 listenerController:new AbortController(), listenerOptions:{}, later:(fn,ms)=>timers.push({fn,ms}),
 parentWindow:{sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
 fetch:async(url,options)=>{
   if (options?.method === 'POST') {
     const body=JSON.parse(options.body);
     writes.push({url,body});
     payload.queues[body.queue].enabled=body.enabled;
     return {ok:true,json:async()=>({enabled:body.enabled})};
   }
   return {ok:true,json:async()=>payload};
 }}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('    const uploadNotices ='),source.indexOf('    const state ='))+
 '\nthis.show=showUploadNotice;this.refresh=refreshStaffProgress;',context);
(async()=>{
 const region=nodes.get('#sc-upload-notices');
 context.show({id:'job',kind:'success',text:'Upload started · Test'});
 assert.equal(region.children.length,1);assert.equal(region.children[0].dataset.kind,'success');
 assert.equal(timers[0].ms,3000);timers.shift().fn();assert.equal(timers[0].ms,200);timers.shift().fn();
 assert.equal(region.children.length,0);
 context.show({id:'job',kind:'success',text:'duplicate'});assert.equal(region.children.length,0);
 context.show({id:'error',kind:'error',text:'Could not upload'});
 assert.equal(timers.length,0);assert.equal(region.children[0].role,'alert');
 region.children[0].children[1].events.click();assert.equal(region.children.length,0);
 context.show({id:'error',kind:'error',text:'same failure'});assert.equal(region.children.length,0);
 payload={online:true,jobs:[{id:'queued',title:'Real title',stage:2,label:'Generating mockups',percent:34,detail:'',storefront:'',updated_at:'now'}]};
 await context.refresh();assert.equal(nodes.get('#sc-os-staff-upload-title').textContent,'Real title');
 assert.equal(nodes.get('#sc-os-staff-upload-meter').value,34);
 payload.jobs[0]={...payload.jobs[0],stage:7,detail:'Dropbox unavailable'};
 await context.refresh();assert.match(region.children[0].children[0].textContent,/Dropbox unavailable/);
 assert(timers.every(t=>t.ms===6000),'errors never schedule dismissal');
 const count=region.children.length;await context.refresh();assert.equal(region.children.length,count);
 payload={online:true,jobs:[{id:'done',title:'Published design',stage:6,label:'Published and PSD mapped',percent:100,
   storefront:'https://example.com/products/exact-handle'}],queues:{design:{waiting:4,enabled:true},upload:{waiting:2,enabled:false}}};
 await context.refresh();
 const design=nodes.get('#sc-os-queue-design'), upload=nodes.get('#sc-os-queue-upload');
 assert.equal(design['aria-label'],'Pause design queue (4 waiting)');
 assert.equal(upload['aria-label'],'Play upload queue (2 waiting)');
 await design.events.click();await upload.events.click();
 assert.deepEqual(writes.map(write=>write.body),[{queue:'design',enabled:false},{queue:'upload',enabled:true}]);
 assert.equal(design['aria-label'],'Play design queue (4 waiting)');
 assert.equal(upload['aria-label'],'Pause upload queue (2 waiting)');
 const links=nodes.get('#sc-os-staff-upload-list').children[0].children[2].children;
 assert.deepEqual(links.map(link=>link.textContent),['View live listing','See in Edition Ops']);
 assert.equal(links[1].href,'/?page=edition_ops&edition_handle=exact-handle');
 nodes.get('#sc-os-staff-uploads').open=true;
 nodes.get('#sc-os-staff-upload-close').events.click();
 assert.equal(nodes.get('#sc-os-staff-uploads').open,false);
 assert.equal(nodes.get('#sc-os-staff-upload-summary').focused,true);
 payload={jobs:[],queues:{design:{waiting:1,enabled:false},upload:{waiting:0,enabled:true}}};
 await context.refresh();
 assert.equal(nodes.get('#sc-os-companion-status').hidden,false);
 assert.equal(nodes.get('#sc-os-staff-uploads').hidden,true);
 assert.equal(upload.hidden,true);
 state.config.staffUploadProgress=false;const prior=timers.length;await context.refresh();assert.equal(timers.length,prior);
 console.log('Upload notices: 3-second success, persistent dismissible errors, deduplication, progress and polling lifecycle passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
