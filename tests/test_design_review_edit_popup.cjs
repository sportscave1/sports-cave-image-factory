const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync('components/design_review_edit.html', 'utf8').replace(/^<script>\s*|\s*<\/script>\s*$/g, '');
const settle = () => new Promise(resolve => setImmediate(resolve));
function fixture({denied = false, failed = false, creating = false} = {}) {
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
  const action = element('a');action.dataset=creating?{designCreate:'true'}:{designReviewPrompt:'/prompt/selected'};action.href='https://designs.example/project';action.closest=()=>card;
  const document = {head:element('head'),body:element('body'),createElement:element,addEventListener:(k,f)=>events[k]=f,execCommand:()=>false,dispatchEvent:()=>{}};
  const ctx = {document, Blob,URL,crypto:{randomUUID:()=> '11111111-2222-4333-8444-555555555555'},location:{origin:'https://os.test'},CustomEvent:class {}, ClipboardItem:class {constructor(data) {this.data=data;}},navigator:{clipboard:{write:async items=>{const text=await (await items[0].data['text/plain']).text();if(denied)throw Error('denied');writes.push(text);}}},
    fetch:async (url,options)=>{requests.push({url,options});return {ok:!failed,json:async()=>failed?{error:'Fetch failed'}:{queued:true,id:'saved-job'}};},
    open:()=>{const tab={location:{replace(url){tab.url=url;}},close(){this.closed=true;}};tabs.push(tab);return tab;}};
  ctx.window=ctx;vm.runInNewContext(code,ctx);
  return {elements,writes,requests,tabs,action,click:()=>events.click({target:{closest:()=>action},preventDefault(){}}),latest:tag=>elements.filter(e=>e.tag===tag).at(-1)};
}
(async()=>{
  const f=fixture();f.click();assert(f.latest('dialog').open);assert.equal(f.requests.length,0);assert.equal(f.tabs.length,0);
  f.elements.find(e=>e.textContent==='Cancel').events.click();assert(f.latest('dialog').removed);assert.equal(f.requests.length,0);
  f.click();f.latest('textarea').value='  Improve the headline <b>without HTML</b>  ';
  const submit=f.latest('form').events.submit;submit({preventDefault(){}});submit({preventDefault(){}});await settle();
  assert.equal(f.requests.length,1);assert.equal(f.tabs.length,0);
  assert.equal(f.requests[0].url,'/api/design-review/edit-queue');
  assert.equal(f.requests[0].options.method,'POST');
  assert.deepEqual(JSON.parse(f.requests[0].options.body),{comments:'Improve the headline <b>without HTML</b>'});
  assert.equal(f.writes.length,0);
  assert.equal(f.action.getAttribute('aria-busy'),undefined);
  const g=fixture({failed:true});g.click();g.latest('textarea').value='Fix spacing';g.latest('form').events.submit({preventDefault(){}});await settle();
  assert.equal(g.tabs.length,0);assert.equal(g.action.getAttribute('aria-busy'),undefined);
  assert(g.elements.some(e=>e.textContent==='Fetch failed'));
  const c=fixture({creating:true});c.click();assert(c.latest('dialog').open);assert(c.latest('textarea').required);
  c.latest('textarea').value='Anthony Edwards dunk and roar';
  const createSubmit=c.latest('form').events.submit;createSubmit({preventDefault(){}});createSubmit({preventDefault(){}});await settle();
  assert.equal(c.requests.length,1);assert.equal(c.requests[0].url,'/api/design-review/create-queue');
  assert.deepEqual(JSON.parse(c.requests[0].options.body),{brief:'Anthony Edwards dunk and roar',request_id:'11111111-2222-4333-8444-555555555555'});
  assert(c.latest('dialog').removed);assert.equal(c.tabs.length,0);
  const e=fixture({creating:true,failed:true});e.click();e.latest('textarea').value='Keep this brief';
  await e.latest('form').events.submit({preventDefault(){}});assert(e.latest('dialog').open);assert.equal(e.latest('textarea').value,'Keep this brief');assert.equal(e.latest('button').disabled,false);
  console.log('PASS: immediate popup, cancel, queued Apply, duplicate submission, original instructions, no manual clipboard handoff and recoverable error.');
})().catch(error=>{console.error(error);process.exitCode=1;});
