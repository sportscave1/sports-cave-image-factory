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
let disconnected=false;
const writes=[];
const context={state, URLSearchParams, icon:name=>name,
 doc:{createElement:()=>new Element(),addEventListener:(event,callback)=>documentEvents[event]=callback},
 root:{querySelector:id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);},classList:{toggle(){}}},
 listenerController:new AbortController(), listenerOptions:{}, later:(fn,ms)=>timers.push({fn,ms}),
 parentWindow:{addEventListener:(event,callback)=>windowEvents[event]=callback,
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
   return {ok:true,json:async()=>payload};
 }}};
vm.createContext(context);
const install = () => vm.runInContext('{'+
 source.slice(source.indexOf('    const uploadNotices ='),source.indexOf('    const state ='))+
 '\nthis.show=showUploadNotice;this.refresh=refreshStaffProgress;}',context);
install();
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
 const status=nodes.get('#sc-os-staff-uploads');
 payload.jobs[0]={...payload.jobs[0],stage:7,detail:'Dropbox unavailable'};
 await context.refresh();
 assert.equal(status.open,false);
 assert.equal(region.children.length,1);
 assert.match(region.children[0].children[0].textContent,/Dropbox unavailable/);
 region.children[0].children[1].events.click();
 assert.match(nodes.get('#sc-os-staff-upload-list').children[0].children[3].textContent,/Dropbox unavailable/);
 assert.equal(writes.length,0,'status polling never restarts a failed upload');
 const summaryReset=nodes.get('#sc-os-staff-upload-reset');
 assert.equal(summaryReset.hidden,false);
 const reset=nodes.get('#sc-os-staff-upload-list').children[0].children[0];
 assert.equal(reset['aria-label'],'Restart upload: Real title');
 await reset.onclick({preventDefault(){},stopPropagation(){}});
 assert.deepEqual(writes[0],{url:'/api/staff-product-uploads/restart',body:{id:'queued',updated_at:'now'}});
 assert.equal(summaryReset.hidden,true);
 writes.length=0;
 payload.jobs[0]={...payload.jobs[0],stage:7,restartable:true};
 await context.refresh();
 await summaryReset.onclick({preventDefault(){},stopPropagation(){}});
 assert.equal(writes.length,1);
 writes.length=0;
 payload.jobs[0]={...payload.jobs[0],stage:7,restartable:true};
 await context.refresh();
 status.open=true;   // Native summary activation.
 payload.jobs[0].detail='Dropbox still unavailable';
 await context.refresh();
 assert.equal(status.open,true);
 documentEvents.click({target:status});
 assert.equal(status.open,true);
 documentEvents.click({target:new Element()});
 assert.equal(status.open,false);
 await context.refresh();
 assert.equal(status.open,false);
 assert.equal(region.children.length,0);
 for(const event of ['pagehide','pageshow','popstate']){
   status.open=true;
   context.show({id:event,kind:'error',text:'Result of an immediate upload action'});
   windowEvents[event]({persisted:true});
   assert.equal(status.open,false);
   assert.equal(region.children.length,0);
 }
 status.open=true;
 const actionNotice={id:'prior-action',kind:'error',text:'Prior action failed'};
 context.show(actionNotice);
 install();  // Same parent DOM, new Streamlit iframe.
 assert.equal(status.open,false);
 assert.equal(region.children.length,0);
 context.show(actionNotice);
 assert.equal(region.children.length,0);
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
 let finishQueueRequest;
 queueResponse=new Promise(resolve=>finishQueueRequest=resolve);
 const oldRequest=design.events.click();
 windowEvents.popstate({});
 finishQueueRequest({ok:false});
 await oldRequest;
 assert.equal(region.children.length,0,'a queue error from the previous page stays dismissed');
 queueResponse=undefined;
 const links=nodes.get('#sc-os-staff-upload-list').children[0].children[2].children;
 assert.deepEqual(links.map(link=>link.textContent),['View live listing','See in Edition Ops']);
 assert.equal(links[1].href,'/?page=edition_ops&edition_handle=exact-handle');
 const postingId='8a8925ad-9a54-4243-9948-62889bd5c1ca';
 payload.jobs[0].ad={label:'Creating the Meta campaign',posting_id:postingId};
 await context.refresh();
 assert.match(nodes.get('#sc-os-staff-upload-stage').textContent,/Published and PSD mapped.*Creating the Meta campaign/);
 assert.equal(nodes.get('#sc-os-staff-upload-meter').value,100);
 assert.equal(nodes.get('#sc-os-staff-upload-list').children[0].children.find(child=>child.textContent==='See in Posting').href,
              '/?page=ads_posting&meta_posting_job='+postingId);
 assert.equal(status.open,false);

 nodes.get('#sc-os-staff-uploads').open=true;
 nodes.get('#sc-os-staff-upload-close').events.click();
 assert.equal(nodes.get('#sc-os-staff-uploads').open,false);
 assert.equal(nodes.get('#sc-os-staff-upload-summary').focused,true);
 payload={jobs:[],queues:{design:{waiting:1,enabled:false},upload:{waiting:0,enabled:true}}};
 await context.refresh();
 assert.equal(nodes.get('#sc-os-companion-status').hidden,false);
 assert.equal(nodes.get('#sc-os-staff-uploads').hidden,true);
 assert.equal(upload.hidden,true);
 payload={online:true,jobs:[],queues:{upload:{waiting:0,enabled:true,display:true},
   design:{waiting:1,enabled:true,jobs:[{id:'design-fixture',title:'Design in progress',state:'running',label:'Generating',percent:45,estimated:true}]},
   ads:{waiting:0,enabled:true,online:true,jobs:[{id:'ad-fixture',title:'Ad in progress',state:'running',label:'Waiting for covers',percent:40}]}}};
 await context.refresh();
 assert.equal(nodes.get('#sc-os-staff-uploads').hidden,false,'idle upload companion remains visible');
 assert.equal(nodes.get('#sc-os-staff-upload-stage').textContent,'Ready');
 assert.equal(nodes.get('#sc-os-design-title').textContent,'Design in progress');
 assert.equal(nodes.get('#sc-os-design-meter')['aria-valuetext'],'Estimated 45% · Generating · 1 waiting');
 assert.equal(nodes.get('#sc-os-ads-meter').value,40);
 const adControl=nodes.get('#sc-os-queue-ads');
 assert.equal(adControl.hidden,false,'active queue can be paused without waiting jobs');
 const beforeWrites=writes.length;
 await adControl.events.click();
 assert.deepEqual(writes[beforeWrites].body,{queue:'ads',enabled:false});
 payload.queues.ads.jobs[0]={...payload.queues.ads.jobs[0],state:'failed',label:'Ad needs attention',detail:'Missing cover',updated_at:'failed-at'};
 await context.refresh();
 assert.equal(nodes.get('#sc-os-ads-status').dataset.state,'failed');
 assert.equal(nodes.get('#sc-os-ads-status').open,false,'polling cannot force open the popup');
 const notices=region.children.length;
 await context.refresh();assert.equal(region.children.length,notices,'failure notice is not repeated');
 assert.ok(nodes.get('#sc-os-ads-list').children[0].children.some(child=>child.textContent==='Ad needs attention · Missing cover'));
 disconnected=true;await context.refresh();
 assert.equal(nodes.get('#sc-os-design-status').dataset.stale,'true');
 assert.equal(nodes.get('#sc-os-design-stage').textContent,'Status unavailable · retrying');
 disconnected=false;await context.refresh();
 assert.equal(nodes.get('#sc-os-design-status').dataset.stale,'false');
 assert.equal(nodes.get('#sc-os-design-title').textContent,'Design in progress');
 payload.queues={};await context.refresh();
 assert.equal(nodes.get('#sc-os-design-card').hidden,true);
 assert.equal(nodes.get('#sc-os-ads-card').hidden,true);
 state.config.staffUploadProgress=false;const prior=timers.length;await context.refresh();assert.equal(timers.length,prior);
 console.log('Upload overlays: one-shot notices, click-only status, dismissal on navigation and remount, progress and queue controls passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
