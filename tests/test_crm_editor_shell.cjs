// Focused interaction checks for presentation controls; no browser dependencies.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('components/crm_sections/composer.js','utf8');
let sent=[],toggle;
for(const visible of [true,false]){
 const context={s:{id:'html-1',visible},name:'HTML Section 1',opened:{},card:{classList:{toggle(){}}},row:{append(){}},
  button:(text,label,onclick)=>toggle={label,onclick,dataset:{},attributes:{},setAttribute(k,v){this.attributes[k]=v;}},emit:(...v)=>sent.push(v)};
 vm.runInNewContext(source.slice(source.indexOf('let visibility='),source.indexOf('let title=')),context);
 assert.equal(toggle.label,(visible?'Hide ':'Show ')+'HTML Section 1');
 assert.equal(toggle.attributes['aria-pressed'],String(visible));
 assert.equal(toggle.dataset.action,'visibility');
 toggle.onclick();assert.equal(sent.at(-1)[0],'visible');assert.equal(sent.at(-1)[1].visible,!visible);
}
const handlers={},attributes={};let active,open=false;
const trigger={setAttribute(k,v){attributes[k]=v;},focus(){active=this;}};
const items=[{focus(){active=this;}},{focus(){active=this;}}];
const menu={open,querySelector:()=>trigger,querySelectorAll:()=>items,contains:n=>n===trigger||items.includes(n),addEventListener:(k,f)=>handlers[k]=f};
const doc={getElementById:()=>menu,addEventListener:(k,f)=>handlers[k]=f,get activeElement(){return active;}};
vm.runInNewContext(source.slice(source.indexOf('const addMenu='),source.indexOf("document.addEventListener('pointerdown'")),{document:doc,addEventListener:(k,f)=>handlers[k]=f,height(){}});
const key=k=>handlers.keydown({key:k,preventDefault(){}});
active=trigger;key('ArrowDown');assert.equal(menu.open,true);assert.equal(active,items[0]);
key('ArrowDown');assert.equal(active,items[1]);key('ArrowUp');assert.equal(active,items[0]);
key('Escape');assert.equal(menu.open,false);assert.equal(active,trigger);
menu.open=true;menu.ontoggle();assert.equal(attributes['aria-expanded'],'true');
handlers.click({target:trigger});assert.equal(menu.open,true);
handlers.click({target:{}});assert.equal(menu.open,false);
menu.open=true;handlers.blur();assert.equal(menu.open,false);
console.log('8 editor visibility/menu keyboard, focus and dismissal scenarios passed');
