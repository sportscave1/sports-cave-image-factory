const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('components/sports_cave_top_bar/index.html','utf8');
const buttons=Object.fromEntries(['back','forward','refresh'].map(name=>[name,{addEventListener(event,fn){this.click=fn;}}]));
const events={};let position=0,reloads=0,cleared=0;const entries=['/?page=dashboard','/?page=orders','/?page=ads-new'];
const navigation={get canGoBack(){return position>0},get canGoForward(){return position<entries.length-1},addEventListener(event,fn){events[event]=fn}};
const context={root:{querySelector:s=>buttons[s.replace('#sc-os-','')]},refreshButton:buttons.refresh,listenerOptions:{},statusCacheKey:()=> 'email',parentWindow:{navigation,addEventListener(event,fn){events[event]=fn},history:{back(){position=Math.max(0,position-1);events.currententrychange()},forward(){position=Math.min(entries.length-1,position+1);events.currententrychange()}},location:{reload(){reloads++}},sessionStorage:{removeItem(){cleared++}}}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('// Native history owns'),source.indexOf('plannerButton.addEventListener("click"')),context);
assert.equal(buttons.back.disabled,true);assert.equal(buttons.forward.disabled,false);
buttons.forward.click();assert.equal(position,1);buttons.forward.click();assert.equal(position,2);assert.equal(buttons.forward.disabled,true);
buttons.back.click();assert.equal(position,1);buttons.back.click();assert.equal(position,0);assert.equal(buttons.back.disabled,true);
buttons.forward.click();buttons.forward.click();buttons.refresh.click();assert.equal(position,2);assert.equal(reloads,1);assert.equal(cleared,1);
for(let i=0;i<10;i++){buttons.back.click();buttons.forward.click();}assert.equal(position,2);
context.parentWindow.navigation=undefined;events.pageshow();assert.equal(buttons.back.disabled,false);assert.equal(buttons.forward.disabled,false);
for(const name of ['Back','Forward','Refresh']){assert.ok(source.includes(`aria-label="${name}" title="${name}"`));}
assert.ok(!source.includes('parentWindow.history.pushState('));
assert.ok(!source.includes('.sc-os-topbar-refresh { display: none; }'));
console.log('Navigation controls: native back/forward, repeated traversal, refresh, reliable disabled state and unsupported API fallback passed.');
