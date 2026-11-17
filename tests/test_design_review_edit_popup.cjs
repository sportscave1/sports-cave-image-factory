const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('components/design_review_edit.html', 'utf8').replace(/^<script>\s*|\s*<\/script>\s*$/g, '');
const settle = () => new Promise(resolve => setImmediate(resolve));
function fixture({denied = false, failed = false} = {}) {
  const events = {}, writes = [], requests = [], tabs = [];
  const elements = [];
  function element(tag) {
    const el = {tag, children:[], attrs:{}, events:{}, value:'', style:{},
      append(...children) { this.children.push(...children); },
      setAttribute(k,v) {this.attrs[k]=v;}, getAttribute(k) {return this.attrs[k];}, removeAttribute(k) {delete this.attrs[k];},
      addEventListener(k,f) {this.events[k]=f;}, focus() {}, select() {}, remove() {this.removed=true;},
      showModal() {this.open=true;}, close() {this.open=false;this.events.close?.();}, querySelector() {return null;}};
    elements.push(el);return el;
  }
  const card = element('card');
  const action = element('a');action.dataset={designReviewPrompt:'/prompt/selected'};action.href='https://designs.example/project';action.closest=()=>card;
  const document = {head:element('head'),body:element('body'),createElement:element,addEventListener:(k,f)=>events[k]=f,execCommand:()=>false};
  const ctx = {document, Blob, ClipboardItem:class {constructor(data) {this.data=data;}},navigator:{clipboard:{write:async items=>{const text=await (await items[0].data['text/plain']).text();if(denied)throw Error('denied');writes.push(text);}}},
    fetch:async url=>{requests.push(url);return {ok:!failed,json:async()=>failed?{error:'Fetch failed'}:{prompt:'ORIGINAL PROMPT\nKeep all existing instructions.'}};},
    open:()=>{const tab={location:{replace(url){tab.url=url;}},close(){this.closed=true;}};tabs.push(tab);return tab;}};
  ctx.window=ctx;vm.runInNewContext(code,ctx);
  return {elements,writes,requests,tabs,action,click:()=>events.click({target:{closest:()=>action},preventDefault(){}}),latest:tag=>elements.filter(e=>e.tag===tag).at(-1)};
}
(async()=>{
  const f=fixture();f.click();assert(f.latest('dialog').open);assert.equal(f.requests.length,0);assert.equal(f.tabs.length,0);
  f.elements.find(e=>e.textContent==='Cancel').events.click();assert(f.latest('dialog').removed);assert.equal(f.requests.length,0);
  f.click();f.latest('textarea').value='  Improve the headline <b>without HTML</b>  ';
  const submit=f.latest('form').events.submit;submit({preventDefault(){}});submit({preventDefault(){}});await settle();
  assert.equal(f.requests.length,1);assert.equal(f.tabs.length,1);assert.equal(f.tabs[0].url,f.action.href);
  assert(f.writes[0].startsWith('ORIGINAL PROMPT\nKeep all existing instructions.\n\n'));
  assert(f.writes[0].includes('Improve the headline <b>without HTML</b>'));assert(f.writes[0].includes('FACIAL FEATURES MUST NEVER CHANGE'));
  assert.equal(f.action.getAttribute('aria-busy'),undefined);
  f.click();assert.equal(f.latest('textarea').value,'');f.latest('form').events.submit({preventDefault(){}});await settle();assert(f.writes[1].includes('No additional changes specified.'));
  for(const options of [{denied:true},{failed:true}]) {
    const g=fixture(options);g.click();g.latest('textarea').value='Fix spacing';g.latest('form').events.submit({preventDefault(){}});await settle();
    assert(g.tabs[0].closed);assert.equal(g.action.getAttribute('aria-busy'),undefined);
    if(options.denied){assert(g.latest('textarea').readOnly);assert(g.latest('textarea').value.includes('Fix spacing'));}
    else assert(g.elements.some(e=>e.textContent==='Fetch failed'));
  }
  console.log('PASS: immediate popup, cancel, Apply, duplicate submission, unchanged base prompt, comments, face protection, blank comments, clipboard fallback and fetch failure.');
})().catch(error=>{console.error(error);process.exitCode=1;});
