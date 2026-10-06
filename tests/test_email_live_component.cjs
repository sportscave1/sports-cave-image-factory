const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {messageMenuItems}=require('../components/support_email/mail.js');
const source=fs.readFileSync('components/support_email/mail.js','utf8');
const shell=fs.readFileSync('components/sports_cave_top_bar/index.html','utf8');
let checks=0;
for(const unread of [true,false])for(const starred of [true,false]){
  const items=messageMenuItems({unread,starred},{archive:'Archive',junk:'Junk',trash:'Trash'});
  assert.ok(items.some(i=>i[1]===(unread?'mark_read':'mark_unread')));checks++;
  assert.ok(items.some(i=>i[1]===(starred?'unstar':'star')));checks++;
  for(const action of ['open','reply','reply_all','forward','move','copy','archive','trash','junk']){
    assert.ok(items.some(i=>i[1]===action&&!i[2]));checks++;
  }
}
assert.ok(messageMenuItems({},{}).find(i=>i[1]==='archive')[2]);checks++;
// Run the real context-target resolver: right click targets a loaded row without opening it.
const ctx={model:{folder:'INBOX',active_message:'selected',threads:[{key:'other-thread',message_key:'other-message',message_unread:true,message_starred:false}],messages:[{key:'selected',folder:'Sent'}]}};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function targetFor('),source.indexOf('function closeMenu('))+';this.target=targetFor;',ctx);
const node={closest(selector){return selector==='[data-key]'?{dataset:{key:'other-thread'}}:null;}};
assert.equal(ctx.target(node).message_key,'other-message');checks++;
assert.equal(ctx.model.active_message,'selected');checks++;
assert.equal(ctx.target({closest(selector){return selector==='[data-folder]'?{dataset:{folder:'Archive'}}:null;}}).folder,'Archive');checks++;
// Execute actual liveTick: busy/hidden/menu and repeated reruns cannot issue more polls.
let polls=0,now=60000;
const live={Date:{now:()=>now},pendingSignal:'',lastLiveCheck:0,busy:false,menu:null,document:{hidden:false},model:{configured:true},emit(action){assert.equal(action,'live_check');polls++;}};
vm.createContext(live);
vm.runInContext(source.slice(source.indexOf('function liveTick('),source.indexOf('// Only standalone'))+';this.tick=liveTick;',live);
live.tick();live.tick();assert.equal(polls,1);checks++;
now=120000;live.busy=true;live.tick();live.busy=false;live.menu={};live.tick();live.menu=null;live.document.hidden=true;live.tick();assert.equal(polls,1);checks++;
live.document.hidden=false;live.tick();assert.equal(polls,2);checks++;
// Mount race: a fallback created before the shell appears must relinquish ownership.
const timers=new Map(),lifecycle={},parent={};let timerId=0;
const timerContext={window:{parent,addEventListener(type,fn){lifecycle[type]=fn;}},liveTick(){},
  setInterval(fn){timers.set(++timerId,fn);return timerId;},clearInterval(id){timers.delete(id);}};
vm.createContext(timerContext);
vm.runInContext(source.slice(source.indexOf('// Only standalone'),source.indexOf('let autosaveTimer=')),timerContext);
assert.equal(timers.size,1);checks++;
parent.SportsCaveTopBar={};[...timers.values()][0]();assert.equal(timers.size,0);checks++;
lifecycle.pagehide();assert.equal(timers.size,0);checks++;
assert.equal((source.match(/setInterval\(/g)||[]).length,1);checks++;
// The shell keeps one scheduler while preserving the original Orders interval.
assert.match(shell,/ORDER_STATUS_REFRESH_MS = 60000/);checks++;
assert.match(shell,/EMAIL_HEARTBEAT_MS = 30000/);checks++;
assert.match(shell,/statusRefreshDelay\("orders", ORDER_STATUS_REFRESH_MS\)/);checks++;
assert.doesNotMatch(shell,/setInterval\(refreshEmailStatus|later\(refreshEmailStatus/);checks++;
assert.match(source,/f\.contentWindow===event\.source&&f\.dataset\.scTopBar==='true'/);checks++;
// Execute the production menu listeners against a tiny DOM fixture.
const handlers={},menuEvents=[],items=[0,1,2].map(i=>({focus(){dom.activeElement=this;},click(){menuEvents.push(i);}}));
const dom={activeElement:items[0],addEventListener(type,fn){handlers[type]=fn;}};
const menus={root:{addEventListener(type,fn){handlers[type]=fn;}},document:dom,
  window:{parent:{document:{addEventListener(type,fn){handlers['parent-'+type]=fn;}}},addEventListener(){}},
  AbortController,menu:null,menuTarget:null,model:{view:'compose'},emit(action){menuEvents.push(action);},
  targetFor(target){return target;},showMenu(target){menus.menu={contains:t=>t===target,querySelectorAll:()=>items};},
  closeMenu(){menus.menu=null;},send(){menuEvents.push('send');}};
vm.createContext(menus);
vm.runInContext(source.slice(source.indexOf("root.addEventListener('contextmenu'"),source.indexOf("window.addEventListener('message'")),menus);
const event=(key,target={closest(){return null;}})=>({key,target,preventDefault(){this.prevented=true;},stopPropagation(){this.stopped=true;}});
let right=event('',{closest(){return null;}});handlers.contextmenu(right);assert.equal(right.prevented,undefined);checks++;
right=event('',{closest(){return node;}});handlers.contextmenu(right);assert.equal(right.prevented,true);assert.ok(menus.menu);checks+=2;
handlers.keydown(event('ArrowDown'));assert.equal(dom.activeElement,items[1]);checks++;
handlers.keydown(event('ArrowUp'));assert.equal(dom.activeElement,items[0]);checks++;
handlers.keydown(event('Enter'));assert.deepEqual(menuEvents,[0]);checks++;
handlers.keydown(event('Escape'));assert.equal(menus.menu,null);assert.deepEqual(menuEvents,[0]);checks+=2;
handlers.contextmenu(right);handlers.pointerdown({target:{}});assert.equal(menus.menu,null);checks++;
handlers.contextmenu(right);handlers['parent-pointerdown']();assert.equal(menus.menu,null);checks++;

// Run the real shared scheduler: three Email ticks, two Orders requests over 60 seconds.
(async()=>{
  let now=300000,checked=0,orders=0,email=0;const scheduled=[];
  const scheduler={state:{config:{ordersEnabled:true,emailEnabled:true,orderStatusUrl:'/fixture/orders'}},
    ORDER_STATUS_REFRESH_MS:60000,EMAIL_HEARTBEAT_MS:30000,
    refreshEmailStatus(){email++;},statusRefreshDelay(){return Math.max(0,60000-(now-checked));},
    writeStatusCache(){checked=now;},requestJson:async()=>{orders++;return {};},
    updateOrdersBadge(){},showOrderToast(){},later(fn,delay){scheduled.push(delay);}};
  vm.createContext(scheduler);
  vm.runInContext(shell.slice(shell.indexOf('const refreshOrderStatus = async'),shell.indexOf('const compactTimerLabel ='))+';this.tick=refreshOrderStatus;',scheduler);
  await scheduler.tick();now+=30000;await scheduler.tick();now+=30000;await scheduler.tick();
  assert.equal(email,3);assert.equal(orders,2);assert.deepEqual(scheduled,[30000,30000,30000]);checks+=3;
  console.log(`Live scheduler, context targeting and menu actions passed (${checks} assertions).`);
})().catch(error=>{console.error(error);process.exitCode=1;});
