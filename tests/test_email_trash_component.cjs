// Execute the production menu, keyboard and confirmation code with a small DOM fake.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {messageMenuItems,trashDeleteTarget,esc}=require('../components/support_email/mail.js');
const source=fs.readFileSync('components/support_email/mail.js','utf8');
let checks=0;
const ok=(condition)=>{assert.ok(condition);checks++;};
const model={view:'mail',folder:'Trash',roles:{trash:'Trash'},selected:'thread',threads:[{key:'thread'}]};
const target={thread_key:'thread',folder:'Trash'};
ok(messageMenuItems(target,model.roles,'Trash').some(i=>i[1]==='request_delete_forever'));
for(const folder of ['INBOX','Sent','Archive','Junk','Drafts','Flagged'])
  ok(!messageMenuItems(target,model.roles,folder).some(i=>i[1]==='request_delete_forever'));
ok(!messageMenuItems({folder:'Trash'},model.roles,'Trash').some(i=>i[1]==='request_delete_forever'));
const blank={closest(){return null;}};
const key=(values={})=>({key:'Delete',target:blank,...values});
ok(trashDeleteTarget(model,key())==='thread');
const row={closest(selector){return selector==='button'||selector==='.conversation'?this:null;}};
ok(trashDeleteTarget(model,key({target:row}))==='thread');
for(const tag of ['input','textarea','select','contenteditable','role="textbox"','role="combobox"','data-email-composer','role="dialog"']){
  const editable={closest(selector){return selector.includes(tag)?this:null;}};
  ok(trashDeleteTarget(model,key({target:editable}))===null);
}
ok(trashDeleteTarget(model,key({target:{isContentEditable:true}}))===null);
for(const flag of ['repeat','ctrlKey','metaKey','altKey','shiftKey'])ok(trashDeleteTarget(model,key({[flag]:true}))===null);
for(const changed of [{view:'compose'},{folder:'INBOX'},{selected:null},{delete_confirmation:{token:'open'}},{error:'offline'}])
  ok(trashDeleteTarget({...model,...changed},key())===null);
ok(trashDeleteTarget(model,key(),true)===null);

const listeners={},events=[];
const ctx={model,busy:false,menu:null,document:{addEventListener(type,fn){listeners[type]=fn;}},
  window:{parent:{document:{addEventListener(){}}},addEventListener(){}},AbortController,
  root:{addEventListener(type,fn){listeners[type]=fn;}},trashDeleteTarget,
  emit(action,data){events.push({action,data});ctx.busy=true;},
  targetFor(){return target;},showMenu(t,x,y){ctx.menu={t,x,y};},closeMenu(){ctx.menu=null;}};
vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf("root.addEventListener('contextmenu'"),source.indexOf("window.addEventListener('message'")),ctx);
listeners.contextmenu({target:{closest(){return row;}},clientX:300,clientY:200,preventDefault(){}});
ok(ctx.menu.t===target&&ctx.menu.x===300&&ctx.menu.y===200);
ctx.menu=null;
const event=key({preventDefault(){this.prevented=true;}});
listeners.keydown(event);listeners.keydown(event);
ok(event.prevented&&events.length===1&&events[0].action==='request_delete_forever');

// The real confirmation defaults to Cancel and emits each token at most once.
let dialog=null;
const dialogEvents=[],buttons=[{dataset:{delete:'cancel'},focus(){this.focused=true;}},{dataset:{delete:'confirm'}}];
const dialogCtx={model:{delete_confirmation:{token:'one',subject:'<script>subject</script>',count:2}},busy:false,esc,
  $(id){return dialog;},closeMenu(){},emit(action,data){dialogEvents.push({action,data});},
  document:{createElement(){return {dataset:{},setAttribute(){},remove(){dialog=null;},showModal(){this.open=true;},
    querySelectorAll(){return buttons;},querySelector(){return buttons[0];}};},body:{append(node){dialog=node;}}}};
vm.createContext(dialogCtx);
vm.runInContext(source.slice(source.indexOf('function renderDeleteConfirmation('),source.indexOf('function closeMenu('))+';this.render=renderDeleteConfirmation;',dialogCtx);
dialogCtx.render();const original=dialog;dialogCtx.render();
ok(dialog===original&&dialog.open&&buttons[0].focused);
ok(dialog.innerHTML.includes('2 messages')&&dialog.innerHTML.includes('This cannot be undone')&&!dialog.innerHTML.includes('<script>'));
dialog.onclick({target:{closest(){return buttons[0];}}});
ok(dialogEvents.length===1&&dialogEvents[0].action==='cancel_delete_forever');
dialogCtx.model.delete_confirmation={token:'two',subject:'Subject',count:1};dialogCtx.render();
dialog.onclick({target:{closest(){return buttons[1];}}});dialog.onclick({target:{closest(){return buttons[1];}}});
ok(dialogEvents.length===2&&dialogEvents[1].action==='confirm_delete_forever'&&dialogEvents[1].data.token==='two');
dialogCtx.model.delete_confirmation=null;dialogCtx.render();ok(dialog===null);
// Context action goes through the same server confirmation; never deletes on menu selection.
const menuEvents=[],menuCtx={menu:null,menuTarget:null,busy:false,pendingAction:'',model,
  esc,messageMenuItems,closeMenu(){menuCtx.menu=null;},emit(action,data){menuEvents.push({action,data});},
  window:{innerWidth:400,innerHeight:300},document:{body:{append(){}},createElement(){return {
    style:{},setAttribute(){},offsetWidth:180,offsetHeight:200,querySelector(){return {focus(){}};},
    getBoundingClientRect(){return {x:216,y:96};}};}}};
vm.createContext(menuCtx);
vm.runInContext(source.slice(source.indexOf('function showMenu('),source.indexOf("root.addEventListener('contextmenu'"))+';this.show=showMenu;',menuCtx);
menuCtx.show(target,399,299);
ok(menuCtx.menu.style.left==='216px'&&menuCtx.menu.style.top==='96px');
ok(menuCtx.menu.innerHTML.includes('Delete forever'));
menuCtx.menu.onclick({target:{closest(){return {dataset:{menuAction:'request_delete_forever'}};}}});
ok(menuEvents.length===1&&menuEvents[0].action==='request_delete_forever'&&menuEvents[0].data.thread_key==='thread');
ok(menuCtx.menu===null);
console.log(`Trash menu, keyboard focus, confirmation and repeat guards passed (${checks} checks).`);
