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
  const ctx={document:doc,parent:{document:doc},AbortController,MutationObserver:class{constructor(fn){mutation=fn;}observe(){}disconnect(){}},
    setTimeout(fn){const id=++sequence;timers.set(id,fn);return id;},clearTimeout(id){timers.delete(id);}};
  ctx.window=ctx;ctx.frameElement=frame;
  vm.runInNewContext(fs.readFileSync('components/product_uploads/mapping.js','utf8'),ctx);
  const panel=ctx.ProductUploadMapping({getRow:()=>row,request:async(path,body,signal)=>{calls.push({path,body,signal});return handler(path,body);}});
  return {panel,el,calls,timers,frame,mutation,dialog:()=>body.children.at(-1),setRow:value=>{row=value;panel.sync(row,true);},respond:fn=>{handler=fn;}};
}
(async()=>{
  const h=harness();h.setRow({id:'first',name:'Captured.psd'});await tick();
  assert.equal(h.el('mapping-status').textContent,'● Unmapped');
  h.respond(async path=>({mapping:{state:'Mapped',psd:'Captured.psd',next_edition:'001',edition_limit:100,product:{title:'Fixture'},worker:'Awaiting preparation'}}));
  h.el('map').onclick();h.el('map').onclick();await tick();
  assert.equal(h.calls.filter(x=>x.path==='map').length,1);
  assert.equal(h.el('mapping-status').textContent,'✓ Mapped');
  const dialog=h.dialog();let prevented=false;dialog.cancel({preventDefault(){prevented=true;}});
  assert(prevented&&!dialog.open&&!dialog.isConnected);assert(h.el('map').focused.preventScroll);
  const before=h.calls.length;await h.el('mapping-refresh').onclick();
  assert.equal(h.calls.length,before+1);assert.equal(h.calls.at(-1).path,'mapping-status?id=first');assert.equal(h.calls.at(-1).body,undefined);
  h.respond(async()=>{throw Error('Network unavailable');});await h.el('mapping-refresh').onclick();
  assert.equal(h.el('mapping-status').textContent,'Status unavailable');
  h.respond(async()=>({mapping:{state:'Pending sync',reason:'Waiting for catalogue'}}));
  h.el('map').onclick();await tick();assert.equal(h.timers.size,1);
  h.dialog().querySelector('[data-field="close"]').onclick();assert.equal(h.timers.size,0);
  let resolve;h.respond(()=>new Promise(r=>resolve=r));h.el('map').onclick();await tick();
  const previous=h.dialog();h.respond(async()=>({mapping:{state:'Unmapped'}}));h.setRow({id:'second',name:'Different.psd'});await tick();
  resolve({mapping:{state:'Mapped',psd:'Captured.psd'}});await tick();
  assert.equal(h.el('mapping-status').textContent,'● Unmapped');assert(!previous.isConnected);
  h.el('map').onclick();await tick();const last=h.dialog();h.frame.isConnected=false;h.mutation();
  assert(!last.isConnected&&!last.open);assert.equal(h.timers.size,0);
  console.log('PASS: read-only refresh; failed status not Unmapped; duplicate clicks; bounded retry cleanup; Escape/focus; stale source response and unmount cleanup.');
})().catch(error=>{console.error(error);process.exitCode=1;});
