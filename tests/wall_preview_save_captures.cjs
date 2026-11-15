// Actual source functions with offline boundaries; no Shopify or Dropbox writes.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const source=fs.readFileSync('shopify_theme/snippets/sc-wall-visualizer-v1.liquid','utf8');
const metadata=source.slice(source.indexOf('function archiveMetadata('),source.indexOf('async function archivePreview('));
const queue=source.slice(source.indexOf('function queuePreviewSave('),source.indexOf('function startPlacementPersistenceInBackground('));
(async()=>{
let product='A',logged=null,known={email:'collector@example.test',name:'',source:'guest'},calls=[],release;
const c={URLSearchParams,state:{clientPreviewId:'initial',sizeInfo:null},sessionId:crypto.randomUUID(),
makeId:()=>crypto.randomUUID(),currentVariant:()=>({id:product}),loggedInIdentity:()=>logged,sessionDownloadIdentity:()=>known,
validIdentityEmail:x=>String(x||'').includes('@'),root:{getAttribute:key=>key==='data-product-id'?product:''},
frameName:()=>'',shareProductUrl:()=>'',saveTail:Promise.resolve(),console,fireLocalPreviewEvent(){},
archiveWithRetry:async(blob,identity,permission,snapshot)=>{calls.push({blob,id:snapshot.get('client_preview_id'),product:snapshot.get('product_id'),email:snapshot.get('customer_email'),permission:snapshot.get('image_reuse_allowed')});if(blob==='hold')await new Promise(r=>release=r);return {archive_status:'queued'};}};
vm.createContext(c);vm.runInContext(metadata+queue,c);
const first=c.queuePreviewSave('hold');await new Promise(r=>setImmediate(r));
let pending=[];for(const p of ['A','A','B','C','D','A']){product=p;pending.push(c.queuePreviewSave('same'));}
release();await Promise.all([first,...pending]);assert.equal(calls.length,7);assert.equal(new Set(calls.map(x=>x.id)).size,7);
assert.deepEqual(calls.map(x=>x.product),['A','A','A','B','C','D','A']);assert(calls.every(x=>x.email==='collector@example.test'));
assert(calls.every(x=>x.permission===null));
logged={email:'logged@example.test',name:'Customer',source:'logged_in'};assert.equal(c.archiveMetadata().get('customer_email'),logged.email);
logged=null;known=null;assert.equal(c.archiveMetadata().get('customer_email'),'');
console.log('PASS repeated identical saves, A/B/C/D/A, immutable queued metadata, known-email fallback, logged-in priority, anonymous and consent separation');
const retry=source.slice(source.indexOf('async function archiveWithRetry('),source.indexOf('function fireLocalPreviewEvent('));
let attempts=0,waits=[],snapshots=[];const snapshot=new URLSearchParams('client_preview_id=retry-id');
const r={window:{setTimeout(fn,ms){waits.push(ms);fn();}},archivePreview:async(...args)=>{snapshots.push(args[4]);if(++attempts===1){const e=new Error('429');e.retryAfterMs=601000;throw e;}return {ok:true};}};
vm.createContext(r);vm.runInContext(retry,r);await r.archiveWithRetry('image',null,null,snapshot);
assert.deepEqual(waits,[601000]);assert.equal(snapshots[0],snapshots[1]);
console.log('PASS rate-limit retry waits for server cooldown and retains exact event identity');
const download=source.slice(source.indexOf('async function downloadConfirmedPreview('),source.indexOf('function shareProductUrl('));
assert(!download.includes('await archivePromise'));assert(download.indexOf('downloadBlob(savedBlob)')<download.indexOf('queuePreviewSave'));
console.log('PASS local Download and next Download are not gated by archive completion');
})().catch(e=>{console.error(e);process.exitCode=1;});
