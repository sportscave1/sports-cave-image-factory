const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('components/sports_cave_top_bar/index.html','utf8');
const task={},time={},strip={hidden:true,querySelector:s=>s.includes('task')?task:time};
let opened=0,greetings=0;
const state={config:{dailyPlannerEnabled:true},plannerTimer:{}};
const context={state,doc:{getElementById:()=>strip},updateTopBarGreeting:()=>greetings++,toolbarTimerLabel:s=>String(s),plannerRemaining:t=>t.remaining_seconds,openDailyPlanner:({focusActive})=>{assert.equal(focusActive,true);opened++;}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('const updateHomeStatus ='),source.indexOf('const updatePlannerMirror ='))+';this.update=updateHomeStatus;',context);
context.update();assert.equal(strip.hidden,true);
for(const status of ['running','paused','expired']){
  state.plannerTimer={id:'one',status,task:'Existing task',remaining_seconds:123};
  const before=JSON.stringify(state.plannerTimer);
  context.update();assert.equal(strip.hidden,false);assert.equal(task.textContent,'Focused on: Existing task');
  assert.equal(JSON.stringify(state.plannerTimer),before,'Home must never mutate timer state');
  strip.onclick();
}
assert.equal(opened,3);
state.plannerTimer.outcome='completed';context.update();assert.equal(strip.hidden,true);
state.plannerTimer={id:'one',status:'running'};state.config.dailyPlannerEnabled=false;context.update();assert.equal(strip.hidden,true);
const greeting=source.slice(source.indexOf('const topBarGreetingForDate ='),source.indexOf('const updateTopBarGreeting ='));
vm.runInContext(greeting+';this.greet=topBarGreetingForDate;',context);
for(const [hour,text] of [[4,'Good night'],[5,'Good morning'],[12,'Good afternoon'],[17,'Good night']])assert.equal(context.greet({getHours:()=>hour}),text);
console.log('Home mirror checks passed: inactive/active/outcome/permissions, navigation, no timer mutation, greeting boundaries.');
// The header registers a click handler only: no Files request or mount at startup.
let click,focused=0;const calls=[];
const launch={filesButton:{addEventListener:(event,fn)=>{assert.equal(event,'click');click=fn;}},state:{config:{filesEnabled:true}},listenerOptions:{},parentWindow:{open:(...args)=>{calls.push(args);return {focus:()=>focused++};}}};
vm.createContext(launch);
vm.runInContext(source.slice(source.indexOf('filesButton.addEventListener("click"'),source.indexOf('const sendPlannerAuth =')),launch);
assert.equal(calls.length,0);click();assert.equal(calls[0][0],'/files-window');assert.equal(calls[0][1],'sports-cave-files-window');assert.equal(focused,1);
launch.state.config.filesEnabled=false;click();assert.equal(calls.length,1);
launch.state.config.filesEnabled=true;launch.parentWindow.open=(...args)=>{calls.push(args);return null;};click();assert.equal(calls.at(-1)[1],'_blank');
console.log('Files checks passed: click-only existing window, permission gate, focus and popup fallback.');
