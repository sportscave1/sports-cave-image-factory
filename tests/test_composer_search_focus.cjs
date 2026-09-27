// Execute the actual production listeners: no browser, mailbox or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('components/sports_cave_top_bar/index.html', 'utf8');
const mail = fs.readFileSync('components/support_email/mail.js', 'utf8');
let checks = 0;
function equal(a,b){assert.equal(a,b);checks++;}
function control(kind, parent=null) {
  return {kind, parent, tagName:kind.toUpperCase(), isContentEditable:kind==='contenteditable',
    closest(selector){return selector.includes(this.kind) ? this : this.parent?.closest(selector);}};
}
const handlers = {};
const searchHandlers = {};
const searchInput = {...control('input'),addEventListener(k,fn){searchHandlers[k]=fn;},focus(){searchHandlers.focus?.();}};
const state = {activePanel:'',visibleResults:[],highlighted:-1};
const ctx = {state,searchInput,listenerOptions:{},root:{contains:target=>target===searchInput},
  doc:{activeElement:null,addEventListener(k,fn){handlers[k]=fn;},body:{classList:{contains(){return false;}}}},
  openSearch(){state.activePanel='search';},openPanel(name){state.activePanel=name;},
  closePanels(){state.activePanel='';searchInput.focus();},renderSearchResults(){},updateHighlight(){},navigate(){},
  sidebarButtonRouteKey(){return '';},closeMobileNavigation(){}};
vm.createContext(ctx);
function runBetween(start,end){vm.runInContext(source.slice(source.indexOf(start),source.indexOf(end)),ctx);}
runBetween('searchInput.addEventListener("click"','mobileSearchButton?.addEventListener');
runBetween('searchInput.addEventListener("input"','notificationsButton.addEventListener');
runBetween('const isEditableSearchEvent =','doc.addEventListener("pointerdown"');
function event(target,key,extras={}){return {target,key,ctrlKey:false,metaKey:false,altKey:false,shiftKey:false,
  preventDefault(){this.defaultPrevented=true;},...extras};}
// Restored/tab focus and generic input cannot open the palette.
searchInput.focus();equal(state.activePanel,'');searchHandlers.input();equal(state.activePanel,'');
searchHandlers.click();equal(state.activePanel,'search');
searchHandlers.keydown(event(searchInput,'Escape'));equal(state.activePanel,'');
const fields=['input','textarea','select','button','contenteditable','[role="textbox"]','[role="combobox"]','[data-email-composer]','.email-composer'];
for(const mode of ['new','reply','reply_all','forward','reopened_draft']) {
  for(const field of fields) {
    const target=control('span',control(field));
    for(const key of [...'john@example.com CC BCC Subject 123 "\'.,/-_?!', 'Enter','Tab','Backspace','Delete','ArrowLeft','Escape']) {
      handlers.keydown(event(target,key));equal(state.activePanel,'');
    }
    for(const modifiers of [{ctrlKey:true},{metaKey:true}]) {
      handlers.keydown(event(target,'k',modifiers));equal(state.activePanel,'');
    }
  }
}
const outside=control('div');
for(const modifiers of [{ctrlKey:true},{metaKey:true}]) {
  handlers.keydown(event(outside,'k',modifiers));equal(state.activePanel,'search');
  handlers.keydown(event(outside,'Escape'));equal(state.activePanel,'');
}
for(const extras of [{isComposing:true},{defaultPrevented:true},{repeat:true},{altKey:true},{shiftKey:true}]) {
  handlers.keydown(event(outside,'k',{ctrlKey:true,...extras}));equal(state.activePanel,'');
}
handlers.keydown(event(outside,'k',{ctrlKey:true,composedPath:()=>[control('[role="textbox"]'),outside]}));equal(state.activePanel,'');
ctx.doc.activeElement={tagName:'IFRAME'};
handlers.keydown(event(outside,'k',{ctrlKey:true}));equal(state.activePanel,'');
ctx.doc.activeElement=null;
// Actual Email shortcuts keep their established send/close behavior and ignore
// single-key actions in editable descendants, token controls and shadow roots.
let emailHandler, sends=0, closes=0, replies=0;
const emailCtx={document:{addEventListener(k,fn){emailHandler=fn;}},model:{view:'compose',active_message:'1'},
  send(){sends++;},emit(){closes++;},compose(){replies++;}};
vm.createContext(emailCtx);
vm.runInContext(mail.slice(mail.indexOf("document.addEventListener('keydown'"),mail.indexOf("window.addEventListener('message'")),emailCtx);
emailHandler(event(control('input'),'Enter',{ctrlKey:true}));equal(sends,1);
emailHandler(event(control('contenteditable'),'Escape'));equal(closes,1);
emailCtx.model.view='mail';
for(const field of fields) for(const key of ['r','f']) emailHandler(event(control('span',control(field)),key));
emailHandler(event(outside,'r',{composedPath:()=>[control('[role="textbox"]'),outside]}));equal(replies,0);
emailHandler(event(outside,'r'));emailHandler(event(outside,'f'));equal(replies,2);
console.log(`Composer/search focus regression passed (${checks} checks).`);
