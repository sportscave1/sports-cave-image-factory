// Navigation lifecycle tests: metadata reads, no automatic mapping mutations.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const elements=new Map(),calls=[],links=[];
const el=id=>{if(!elements.has(id))elements.set(id,{});return elements.get(id);};
let respond=async()=>({mapping:{url:'/?page=edition_ops&edition_product=gid%3A%2F%2Fshopify%2FProduct%2F123',state:'Available in Edition Ops',reason:'Use Add / Attach PSD in Edition Ops.'}});
const context={document:{getElementById:el,createElement(){const link={click(){links.push(this);}};return link;}},URL};
context.window=context;context.location={origin:'http://fixture'};
vm.runInNewContext(fs.readFileSync('components/product_uploads/mapping.js','utf8'),context);
const panel=context.ProductUploadMapping({request:async(...args)=>{calls.push(args);return respond();},getRow:()=>({id:'one'})});
(async()=>{
 panel.sync({id:'one'},true);assert.equal(calls.length,0);assert.equal(el('map').textContent,'Mapping');
 await el('map').onclick();assert.equal(calls.length,1);assert.equal(calls[0][0],'mapping-status?id=one');assert.equal(calls[0].length,1);
 assert.equal(links.length,1);assert.equal(links[0].target,'_top');assert(links[0].href.includes('page=edition_ops'));
 respond=async()=>({mapping:{url:'/?page=edition_ops&edition_search=Tempted',state:'Pending / not found in Edition Ops',reason:'No PSD was attached.'}});
 await el('mapping-refresh').onclick();assert.equal(el('mapping-status').textContent,'Pending / not found in Edition Ops');assert.equal(links.length,1);
 await el('map').onclick();assert.equal(links.length,2);assert(!el('mapping-status').textContent.includes('Success'));
 let resolve;respond=()=>new Promise(r=>{resolve=r;});
 const pending=el('map').onclick();panel.sync({id:'two'},true);resolve({mapping:{url:'/?page=edition_ops',state:'old'}});await pending;
 assert.equal(links.length,2,'stale result must not navigate another upload');
 respond=async()=>{throw Error('offline');};await el('map').onclick();assert.equal(el('mapping-status').textContent,'Status unavailable');
 panel.dispose();assert(el('map').disabled);console.log('Mapping navigation checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
