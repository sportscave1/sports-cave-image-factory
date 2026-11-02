const vm=require('node:vm'), fs=require('node:fs'), assert=require('node:assert/strict');
const {webcrypto,createHash}=require('node:crypto');
const box={crypto:webcrypto,TextEncoder};
vm.runInNewContext(fs.readFileSync(__dirname+'/../edge-adapter/prepared-context.js','utf8'),box);
const api=box.SportsCavePreparedContext;
const context={kind:'product_uploads',workflow:'28a11c57-a019-4412-b509-1275b49f26ad',name:'Test product',category:'id:category',source:'a'.repeat(64),source_id:'id:source',revision:'0165e87b07fed27000000036d367e13'};
const node=()=>({dataset:{ready:'true',context:JSON.stringify(context)}});
const settle=n=>new Promise(resolve=>{const value=api.read(n,()=>resolve(api.read(n,()=>{})));if(value)resolve(value);});
(async()=>{
 const n=node(); const expected=createHash('sha256').update(api.canonical(n.dataset)).digest('hex');
 assert.equal(api.read(n,()=>{}),null); await new Promise(r=>setTimeout(r,20)); assert.equal(api.read(n,()=>{}),expected);
 assert.equal(api.read(node(),()=>{throw new Error('Unexpected rehash');}),expected,'identical replacement retains verified scope');
 const invalidReplacement=node();invalidReplacement.dataset.ready='false';assert.equal(api.read(invalidReplacement,()=>{}),null);
 const matching=node();matching.dataset.productSha256=expected;assert.equal(await settle(matching),expected);
 const conflicting=node();conflicting.dataset.productSha256='b'.repeat(64);assert.equal(await settle(conflicting),null);
 for(const field of Object.keys(context)){const n=node(),c={...context};delete c[field];n.dataset.context=JSON.stringify(c);assert.equal(api.canonical(n.dataset),null,field);}
 const notReady=node();notReady.dataset.ready='false';assert.equal(api.read(notReady,()=>{}),null);
 const changing=node();const original=await settle(changing);changing.dataset.context=JSON.stringify({...context,revision:'0165e87b07fed27000000036d367e14'});
 assert.equal(api.read(changing,()=>{}),null);await new Promise(r=>setTimeout(r,20));assert.notEqual(api.read(changing,()=>{}),original);
 const pending=node();api.read(pending,()=>{});pending.dataset.ready='false';await new Promise(r=>setTimeout(r,20));assert.equal(api.read(pending,()=>{}),null);
 const unicode=node();unicode.dataset.context=JSON.stringify({...context,name:'Shane — Final Bow'});assert.ok(await settle(unicode));
 console.log('PASS prepared context: complete legacy marker, matching/conflicting hashes, missing fields, not-ready, revision change, asynchronous invalidation, Unicode');
})().catch(e=>{console.error(e);process.exitCode=1;});
