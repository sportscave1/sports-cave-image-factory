const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const core=require('../components/orders_prodigi_grid/grid-core.js');
const live=fs.readFileSync(require('node:path').join(__dirname,'../components/orders_prodigi_grid/live.js'),'utf8');
const row=(id,revision='a')=>({id:'allocation:'+id,revision:revision.repeat(64),unit_key:'unit:'+id,cells:{order:'#'+id,product:'Synthetic artwork'},review:{status:'Queued',allocation_id:String(id)}});

test('new arrivals retain unchanged rows, exact selection and opened review',()=>{
 const old=[row(1),row(2)],fresh=row(3,'b');
 const result=core.mergeDelta(old,{order:[fresh.id,...old.map(r=>r.id)],rows:[fresh],removed:[]},new Set([old[1].id]),old[1].id);
 assert.equal(result.rows[1],old[0]);assert.equal(result.rows[2],old[1]);
 assert.deepEqual([...result.selected],[old[1].id]);assert.equal(result.opened,old[1].id);assert.deepEqual([...result.changed],[fresh.id]);
});

test('an in-flight snapshot cannot roll progress back or remove a complete certificate',()=>{
 const old=row(1);old.review={status:'Complete',allocation_id:'1',updated_at:'2026-11-22T09:00:00Z'};old.cells.prodigi='Complete';
 const fresh=row(1,'b');fresh.review.updated_at='2026-11-22T08:00:00Z';
 const result=core.mergeDelta([old],{order:[old.id],rows:[fresh],removed:[]},new Set(),old.id);
 assert.equal(result.rows[0].review.status,'Complete');assert.equal(result.rows[0].cells.prodigi,'Complete');
 assert.equal(result.rows[0].certificate,'/api/orders/certificate?allocation_id=1');
});

test('allocation arrival transfers selection by one immutable unit, never customer name',()=>{
 const old={...row(1),id:'unit:original'},fresh={...row(9,'b'),unit_key:old.unit_key};
 const result=core.mergeDelta([old],{order:[fresh.id],rows:[fresh],removed:[old.id]},new Set([old.id]),old.id);
 assert.deepEqual([...result.selected],[fresh.id]);assert.equal(result.opened,fresh.id);assert.equal(result.rows.length,1);
 fresh.unit_key='unit:different';fresh.cells.customer=old.cells.customer='Same name';
 const separate=core.mergeDelta([old],{order:[fresh.id],rows:[fresh],removed:[old.id]},new Set([old.id]),old.id);
 assert.equal(separate.opened,old.id);assert.equal(separate.rows[1].detached,true);assert.equal(separate.rows[1].review.can_reset,false);
});

test('an open row leaving the latest window stays visible read-only',()=>{
 const old=row(1),fresh=row(2,'b');old.review.can_reset=true;
 const result=core.mergeDelta([old],{order:[fresh.id],rows:[fresh],removed:[old.id]},new Set(),old.id);
 assert.equal(result.rows.length,2);assert.equal(result.rows[1].review.status,'Outside current results');assert.equal(result.rows[1].review.can_reset,false);
 assert.equal(old.review.can_reset,true);
});

test('invalid or incomplete deltas cannot corrupt current rows',()=>{
 const old=row(1);const before=JSON.stringify(old);
 for(const delta of [{order:['missing'],rows:[],removed:[]},{order:[old.id,old.id],rows:[],removed:[]},{order:[old.id],rows:[],removed:[old.id]}])assert.throws(()=>core.mergeDelta([old],delta,new Set(),old.id));
 assert.equal(JSON.stringify(old),before);
});

test('page anchoring preserves the viewed row through insertions and partial-page removals',()=>{
 const rows=Array.from({length:103},(_,i)=>row(i)),arrivals=[row(200),row(201),...rows];
 assert.equal(core.anchoredPage(arrivals,1,rows[50].id),1);
 assert.equal(core.anchoredPage(arrivals,0,rows[49].id),1);
 assert.equal(core.anchoredPage(rows.slice(0,49),2,''),0);
});

test('status polling includes the open and visible later-page units within its existing budget',()=>{
 const rows=Array.from({length:350},(_,i)=>row(i+1));
 const ids=core.statusIds(rows,'allocation:325','all',6);
 assert.equal(ids[0],'325');assert(ids.includes('301')&&ids.includes('350'));assert.equal(ids.length,200);
});

test('keyed DOM insertion keeps unrelated rows and restores the viewport anchor',()=>{
 const old=Array.from({length:53},(_,i)=>row(i));
 const body={children:[],insertBefore(element,before){if(element.parentNode===this)this.children.splice(this.children.indexOf(element),1);const at=before?this.children.indexOf(before):this.children.length;this.children.splice(at,0,element);element.parentNode=this;}};
 const wrap={scrollTop:80,getBoundingClientRect:()=>({top:100}),querySelector:s=>s==='tbody'?body:null,querySelectorAll:()=>body.children};
 function element(data){return {dataset:{unitId:data.id},parentNode:null,remove(){body.children.splice(body.children.indexOf(this),1);this.parentNode=null;},replaceWith(next){const at=body.children.indexOf(this);body.children[at]=next;next.parentNode=body;this.parentNode=null;},getBoundingClientRect(){const top=140+body.children.indexOf(this)*40-wrap.scrollTop;return {top,bottom:top+40};}};}
 body.children=old.slice(0,50).map(element);for(const child of body.children)child.parentNode=body;const retained=body.children[3];
 const scope=vm.createContext({args:{rows:old},page:0,filter:'all',query:'',selected:new Set(),opened:'',SIZE:50,core,rememberedScroll:80,
  document:{activeElement:{id:''},querySelector:s=>s==='.scroll'?wrap:null,querySelectorAll:()=>[],getElementById:()=>null},
  render:()=>assert.fail('No whole table rebuild'),orderRow:element,remember(){},height(){},setInterval,clearInterval});
 vm.runInContext(live,scope);const anchor=vm.runInContext('viewportAnchor()',scope);
 const first=row(200,'b'),second=row(201,'b');scope.args.rows=[first,second,...old];scope.anchor=anchor;scope.changed=new Set([first.id,second.id]);
 vm.runInContext('patchLiveListing(changed,anchor)',scope);
 assert.equal(body.children[5],retained);assert.equal(wrap.scrollTop,160);assert.equal(body.children.length,50);
});

test('feed failures retain table state and late search responses are ignored',async()=>{
 const old=row(1);let finish;const events=[];
 const scope=vm.createContext({args:{rows:[old],feed:{scope:'old',query:'old'}},page:0,filter:'all',query:'',opened:old.id,selected:new Set([old.id]),inView:true,core,SIZE:50,
  document:{hidden:false,querySelector:()=>null},Date,AbortController,setTimeout,clearTimeout,setInterval,clearInterval,
  fetch:()=>new Promise(resolve=>{finish=resolve;}),event:(...e)=>events.push(e),selectionChanged:()=>assert.fail('Selection must stay local')});
 vm.runInContext(live,scope);const pending=vm.runInContext('refreshFeed()',scope);await new Promise(resolve=>setImmediate(resolve));
 scope.args={...scope.args,feed:{scope:'new',query:'new'}};
 finish({ok:true,json:async()=>({version:'a'.repeat(64),order:[],rows:[],removed:[old.id]})});await pending;
 assert.equal(scope.args.rows[0],old);assert.equal(events.length,0);
 scope.fetch=async()=>({ok:false});await vm.runInContext('refreshFeed()',scope);
 assert.equal(scope.args.rows[0],old);assert.equal(scope.opened,old.id);assert.equal(vm.runInContext('feedDelayed',scope),true);
});
