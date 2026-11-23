const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../shopify_customer_account/extensions/customer-certificate-vault/src/frame-offer-loader.js'),'utf8');
const load=()=>import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

test('page warmup and simultaneous popup opens share one bootstrap and country price read',async()=>{
 const {createFrameOfferLoader}=await load();let boot=0,price=0;
 const loader=createFrameOfferLoader({bootstrap:async()=>{boot++;return {certificates:['owner'],frame_product:{available:true}}},prices:async(p,c)=>{price++;return {...p,country:c}}});
 const [page,a,b]=await Promise.all([loader.bootstrap(),loader.context('AU'),loader.context('AU')]);
 assert.equal(boot,1);assert.equal(price,1);assert.equal(a,b);assert.equal(a.certificates,page.certificates);
 await loader.context('AU');assert.equal(boot,1);assert.equal(price,1);
});
test('country prices never cross markets and cache expiry refreshes both reads',async()=>{
 const {createFrameOfferLoader}=await load();let time=0,boot=0;const countries=[];
 const loader=createFrameOfferLoader({now:()=>time,ttl:60,bootstrap:async()=>{boot++;return {frame_product:{available:true}}},prices:async(p,c)=>{countries.push(c);return {...p,country:c}}});
 assert.equal((await loader.context('AU')).frame_product.country,'AU');
 assert.equal((await loader.context('US')).frame_product.country,'US');
 assert.equal(boot,1);assert.deepEqual(countries,['AU','US']);
 time=61;await loader.context('AU');assert.equal(boot,2);assert.deepEqual(countries,['AU','US','AU']);
});
test('failed warmup can retry and does not poison the account session',async()=>{
 const {createFrameOfferLoader}=await load();let count=0;
 const loader=createFrameOfferLoader({bootstrap:async()=>{if(++count===1)throw Error('offline');return {frame_product:{available:false}}},prices:()=>{throw Error('must not query unavailable product')}});
 await assert.rejects(loader.context('AU'),/offline/);
 assert.equal((await loader.context('AU')).frame_product.available,false);assert.equal(count,2);
});
test('price failure retries without repeating a successful bootstrap',async()=>{
 const {createFrameOfferLoader}=await load();let boot=0,price=0;
 const loader=createFrameOfferLoader({bootstrap:async()=>{boot++;return {frame_product:{available:true}}},prices:async p=>{if(++price===1)throw Error('price');return p}});
 await assert.rejects(loader.context('AU'),/price/);await loader.context('AU');assert.equal(boot,1);assert.equal(price,2);
});
test('separate mounted accounts never share cached certificates',async()=>{
 const {createFrameOfferLoader}=await load();
 const forOwner=owner=>createFrameOfferLoader({bootstrap:async()=>({certificates:[owner]}),prices:async p=>p});
 const a=forOwner('A'),b=forOwner('B');
 assert.deepEqual((await a.context('AU')).certificates,['A']);assert.deepEqual((await b.context('AU')).certificates,['B']);
});
