const {test}=require('node:test');
const assert=require('node:assert/strict');
const {transfer,targetPath}=require('../shopify_theme/assets/sports-cave-certificate-cart.js');
const origin='https://www.sportscaveshop.com';
test('returns only safe storefront paths and opens drawer',()=>{
 for(const value of ['https://evil.example/x','/account','/checkout']) assert.equal(targetPath(value,origin),'/collections/all-sports-wall-art?sc_cart=1');
 assert.equal(targetPath('/products/test?size=S',origin),'/products/test?size=S&sc_cart=1');
});
for(const present of [false,true]) test(`preserves existing cart and deduplicates certificate: ${present}`,async()=>{
 const calls=[];const request='test-request';const existing={variant_id:33,quantity:2,properties:{}};
 const item={ok:true,variant_id:'68066069938483',request_reference:request,properties:{_sports_cave_frame_request:request}};
 const fetch=async(url,options={})=>{calls.push({url,options});
  const value=url.endsWith('cart.js')?{items:[existing,...(present?[{variant_id:item.variant_id,quantity:1,properties:item.properties}]:[])]}:item;
  return {ok:true,json:async()=>value};};
 assert.equal(await transfer('signed',{fetch,origin,lastPage:'/products/previous'}),'/products/previous?sc_cart=1');
 assert.equal(calls.filter(c=>c.url.endsWith('cart/add.js')).length,present?0:1);
 assert.ok(calls.every(c=>!c.url.includes('clear')&&!c.url.includes('update')));
 if(!present)assert.deepEqual(JSON.parse(calls[2].options.body).items,[{id:Number(item.variant_id),quantity:1,properties:item.properties}]);
});
test('refused handoff does not touch storefront cart',async()=>{
 let calls=0;await assert.rejects(transfer('invalid',{fetch:async()=>{calls++;return {ok:false,json:async()=>({ok:false})};},origin}));assert.equal(calls,1);
});
