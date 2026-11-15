// Local adapter contracts: no real network, theme changes, pixels or email delivery.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const crypto=require('node:crypto');
function fixture(fetch) {
  const events=[],statuses=[],storage=new Map();
  const window={dispatchEvent:e=>events.push(e)};
  vm.runInNewContext(fs.readFileSync('docs/storefront/wall-preview-crm-v2.js','utf8'),{
    window,sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},crypto,
    CustomEvent:class {constructor(name,options){this.name=name;this.detail=options.detail;}},
    URLSearchParams,AbortController,Blob,File,fetch,
    setTimeout:(fn,ms)=>ms>=30000 ? 1 : (queueMicrotask(fn),2),clearTimeout:()=>{}
  });
  const hooks={metadata:()=>({product_id:'123',variant_id:'456',customer_email:undefined,product_url:'https://sportscaveshop.com/products/a'}),
    compositeBlob:async()=>new Blob(['finished composite'],{type:'image/jpeg'}),showActions:()=>{},showConfirm:()=>{},
    archiveStatus:s=>statuses.push(s),downloadBlob:()=>{}};
  return {adapter:window.SportsCaveWallPreviewCRM(hooks),events,statuses,storage};
}
async function main() {
  let calls=0,posted;
  const f=fixture(async(url)=>{if(url.includes('/analytics/'))return {ok:true};calls++;posted=url;return {ok:true,json:async()=>({ok:true,preview_id:'server-preview',preview_token:'private',share_url:'https://example.test/share'})};});
  f.adapter.newWallPhoto();f.adapter.placementChanged();assert.equal(calls,0);
  await Promise.all([f.adapter.confirm(),f.adapter.confirm()]);assert.equal(calls,1);
  assert.equal(new URL(posted).searchParams.has('customer_email'),false);
  const props=f.adapter.cartProperties({existing:'preserved'});
  assert.equal(props.existing,'preserved');assert.equal(props._wall_preview_id,'server-preview');
  assert.ok(props._wall_preview_client_id);
  assert.ok(f.events.every(e=>!('session_id' in e.detail) && !('email' in e.detail)));
  let release,started;
  const active=new Promise(resolve=>{started=resolve;});
  const race=fixture(async(url)=>{if(url.includes('/analytics/'))return {ok:true};started();await new Promise(resolve=>{release=resolve;});return {ok:true,json:async()=>({ok:true,preview_id:'old-wall'})};});
  race.adapter.newWallPhoto();const pending=race.adapter.confirm();await active;
  race.adapter.newWallPhoto();release();await pending;
  assert.equal(race.adapter.cartProperties()._wall_preview_id,undefined);
  let retries=0;
  const failing=fixture(async(url)=>{if(url.includes('/analytics/'))throw new Error('Analytics offline');retries++;throw new Error('network unavailable');});
  failing.adapter.newWallPhoto();await failing.adapter.confirm();assert.equal(retries,3);
  assert.ok(failing.statuses.some(s=>s.includes('server save failed')));
  assert.equal(failing.adapter.cartProperties()._wall_preview_id,undefined);
  console.log('Wall Preview adapter: 6 contract checks passed');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
