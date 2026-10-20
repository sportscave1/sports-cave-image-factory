// Component lifecycle unit tests; no browser/server/provider access.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function harness(){
  const elements=new Map(),timers=new Map(),calls=[];let sequence=0,row={id:'first',name:'Captured.psd'},handler=async()=>({mapping:{state:'Unmapped'}}),mutation;
  class Element{
    constructor(){this.style={};this.dataset={};this.children=[];this.fields=new Map();this.isConnected=true;this.value='';}
    set innerHTML(value){this.html=value;for(const match of value.matchAll(/data-field="([^"]+)"/g))this.fields.set(match[1],new Element());}
    querySelector(selector){return this.fields.get(selector.match(/data-field="([^"]+)"/)[1]);}
    querySelectorAll(){return this.querySelector('[data-field="choices"]')?.children||[];}
    append(...children){this.children.push(...children);}replaceChildren(...children){this.children=children;}
    setAttribute(){}addEventListener(event,handler){this[event]=handler;}showModal(){this.open=true;}close(){this.open=false;}
    remove(){this.isConnected=false;}focus(options){this.focused=options;}reportValidity(){return true;}
  }
  const el=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const body=new Element(),frame=new Element(),doc={body,getElementById:el,createElement(){const e=new Element();e.ownerDocument=doc;return e;}};
  const host={document:doc,location:{href:'http://fixture/?page=product_uploads'},history:{replaceState(state,unused,url){host.location.href=String(url);}}};
  const ctx={document:doc,parent:host,URL,AbortController,MutationObserver:class{constructor(fn){mutation=fn;}observe(){}disconnect(){}},
    setTimeout(fn){const id=++sequence;timers.set(id,fn);return id;},clearTimeout(id){timers.delete(id);}};
  ctx.window=ctx;ctx.frameElement=frame;
  vm.runInNewContext(fs.readFileSync('components/product_uploads/mapping.js','utf8'),ctx);
  const panel=ctx.ProductUploadMapping({getRow:()=>row,request:async(path,body,signal)=>{calls.push({path,body,signal});return handler(path,body);}});
  return {panel,el,calls,timers,frame,mutation,host,dialog:()=>body.children.at(-1),setRow:value=>{row=value;panel.sync(row,true);},respond:fn=>{handler=fn;}};
}
(async()=>{
  const saved=id=>({id,name:'Captured.psd',saved_source_version:'saved-'+id,mode:'DRAFT'});
  const h=harness();h.setRow(saved('first'));await tick();
  assert.equal(h.el('mapping-status').textContent,'Unmapped');assert.equal(h.calls.length,0,'mount must do no work');
  h.respond(async path=>({mapping:{state:path==='map'?'Mapping…':'Unmapped',stage:'Finding product in Edition Ops'}}));
  h.el('map').onclick();h.el('map').onclick();await tick();await tick();
  assert.equal(h.calls.filter(x=>x.path==='map').length,1);assert(h.host.location.href.includes('upload=first'));
  assert.equal(h.calls.at(-1).body.source_version,'saved-first');assert.equal(h.timers.size,1);
  const dialog=h.dialog();let prevented=false;dialog.cancel({preventDefault(){prevented=true;}});
  assert(prevented&&!dialog.open&&!dialog.isConnected);assert(h.el('map').focused.preventScroll);
  assert.equal(h.timers.size,1,'closing retains read-only polling; backend is not cancelled');
  h.respond(async()=>({mapping:{state:'Mapped',psd:'Live/Captured.psd',edition_id:1,run_id:2,preparation_held:true,completed:[]}}));
  await h.el('mapping-refresh').onclick();assert.equal(h.el('mapping-status').textContent,'✓ Success — PSD mapped');assert.equal(h.timers.size,0);
  h.el('map').onclick();await tick();assert(h.dialog().open);
  assert.equal(h.calls.filter(x=>x.path==='map').length,1,'reopen reads actual state');
  h.respond(async()=>{throw Error('Network unavailable');});await h.el('mapping-refresh').onclick();assert.equal(h.el('mapping-status').textContent,'Status unavailable');
  h.dialog().querySelector('[data-field="close"]').onclick();
  let resolve;h.respond(()=>new Promise(r=>resolve=r));h.el('map').onclick();await tick();
  const previous=h.dialog();h.setRow(saved('second'));resolve({mapping:{state:'Mapped'}});await tick();
  assert.equal(h.el('mapping-status').textContent,'Unmapped');assert(!previous.isConnected);
  h.respond(async()=>({mapping:{state:'Waiting for product in Edition Ops',reason:'Waiting for product in Edition Ops'}}));
  h.el('map').onclick();await tick();assert.equal(h.timers.size,0,'not-found needs explicit Retry');
  h.setRow({...saved('second'),saved_source_version:'new-save'});await tick();assert(!h.dialog().isConnected);
  h.el('map').onclick();await tick();const last=h.dialog();h.frame.isConnected=false;h.mutation();
  assert(!last.isConnected&&!last.open);assert.equal(h.timers.size,0);h.panel.clearRecoveryURL();assert(!h.host.location.href.includes('upload='));
  const pick=harness();pick.setRow(saved('choice'));
  pick.respond(async path=>({mapping:path==='map'?{state:'Mapping…',stage:'Moving PSD'}:{state:'Waiting for product in Edition Ops',needs_product:true,candidates:[{id:'gid://shopify/Product/987',title:'Confirmed artwork'}]}}));
  pick.el('map').onclick();await tick();
  assert.equal(pick.calls.filter(x=>x.path==='map').length,0,'ambiguous identity must not submit automatically');
  pick.dialog().querySelector('[data-field="product-choice"]').value='gid://shopify/Product/987';
  pick.dialog().querySelector('[data-field="retry"]').onclick();await tick();
  assert.equal(pick.calls.at(-1).body.product_id,'gid://shopify/Product/987');
  assert.equal(pick.calls.at(-1).body.confirm_product,true);
  assert.equal(pick.el('map').textContent,'Linking PSD');assert(pick.el('map').disabled);
  assert.equal(pick.dialog().querySelector('[data-field="steps"]').children.length,2);
  pick.panel.dispose();
  const waiting=harness();waiting.setRow(saved('waiting'));
  waiting.respond(async()=>({mapping:{state:'Waiting for product in Edition Ops',needs_product:true,candidates:[]}}));
  waiting.el('map').onclick();await tick();
  waiting.dialog().querySelector('[data-field="retry"]').onclick();await tick();
  assert.equal(waiting.calls.at(-1).path,'map');
  assert.equal(waiting.calls.at(-1).body.product_id,undefined);
  waiting.panel.dispose();
  console.log('PASS: no mount requests; explicit start; double-click; non-cancelling close; recovery; failure never green; stale operation/save fencing; timers and unmount.');
})().catch(error=>{console.error(error);process.exitCode=1;});
