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
test('refused handoff never mutates storefront cart',async()=>{
 const calls=[];await assert.rejects(transfer('invalid',{fetch:async(url,options={})=>{calls.push({url,options});return {ok:false,json:async()=>({ok:false})};},origin}));
 assert.equal(calls.length,2);assert.ok(calls.every(c=>!c.url.endsWith('cart/add.js')));
});

for(const present of [false,true])test(`account cart goes directly to checkout after merging, already present: ${present}`,async()=>{
 const calls=[];const item={ok:true,destination:'checkout',variant_id:'68066069938483',request_reference:'certificate',properties:{_sports_cave_frame_request:'certificate'}};
 const fetch=async(url,options={})=>{calls.push({url,options});return {ok:true,json:async()=>url.endsWith('cart.js')?{items:present?[{variant_id:item.variant_id,quantity:1,properties:item.properties}]:[]}:item};};
 assert.equal(await transfer('signed',{fetch,origin,root:'/en-us/',lastPage:'/products/previous'}),'/en-us/checkout');
 assert.equal(calls.filter(c=>c.url.endsWith('cart/add.js')).length,present?0:1);
 assert.ok(calls.every(c=>!c.url.includes('clear')&&!c.url.includes('update')));
});

const certificate={ok:true,variant_id:'68066069938483',request_reference:'certificate',properties:{_sports_cave_frame_request:'certificate',Certificate:'Fixture edition',Edition:'#027 of 100'}};
const response=value=>({ok:true,json:async()=>value});
test('add returns both rendered sections and updates the drawer without another navigation or fetch',async()=>{
 const calls=[];let merged;
 const fetch=async(url,options={})=>{calls.push({url,options});return response(url.endsWith('cart.js')?{items:[]}:
  url.endsWith('cart/add.js')?{sections:{header:'<header/>',drawer:'<cart-form/>'}}:certificate);};
 await transfer('signed',{fetch,origin,sections:['header','drawer'],path:'/products/previous',onCart:value=>{merged=value}});
 assert.equal(calls.length,3);assert.deepEqual(merged.sections,{header:'<header/>',drawer:'<cart-form/>'});
 const payload=JSON.parse(calls[2].options.body);assert.deepEqual(payload.sections,['header','drawer']);assert.equal(payload.sections_url,'/products/previous');
 assert.equal(payload.items[0].properties.Certificate,'Fixture edition');
});
test('an accepted add with a lost response is reconciled and never replayed',async()=>{
 let reads=0,adds=0,merged;
 const fetch=async(url)=>{
  if(url.endsWith('cart.js'))return response({items:++reads===1?[]:[{variant_id:certificate.variant_id,quantity:1,properties:certificate.properties}]});
  if(url.endsWith('cart/add.js')){adds++;throw new Error('lost response');}
  if(url.includes('?sections='))return response({drawer:'<cart-form/>'});
  return response(certificate);
 };
 await transfer('signed',{fetch,origin,sections:['drawer'],onCart:value=>{merged=value}});
 assert.equal(adds,1);assert.equal(reads,2);assert.equal(merged.sections.drawer,'<cart-form/>');
});
test('missing section HTML refetches display only, including for an existing certificate',async()=>{
 const calls=[];
 const fetch=async(url)=>{calls.push(url);return response(url.endsWith('cart.js')?{items:[{variant_id:certificate.variant_id,quantity:1,properties:certificate.properties}]}:
  url.includes('?sections=')?{drawer:'<cart-form/>'}:certificate);};
 await transfer('signed',{fetch,origin,sections:['drawer']});assert.equal(calls.length,3);assert.ok(calls.every(url=>!url.endsWith('cart/add.js')));
});
test('a rejected add is not reported as success, and a retry rechecks the cart',async()=>{
 let adds=0,complete=0;
 const fetch=async(url)=>{
  if(url.endsWith('cart.js'))return response({items:[]});
  if(url.endsWith('cart/add.js')){adds++;return {ok:false,json:async()=>({description:'Unavailable'})};}
  return response(certificate);
 };
 await assert.rejects(transfer('signed',{fetch,origin,onCart:()=>complete++}),/Unavailable/);
 assert.equal(adds,1);assert.equal(complete,0);
});
test('mismatched private request properties cannot mutate the cart',async()=>{
 let adds=0;
 const fetch=async(url)=>{if(url.endsWith('cart/add.js'))adds++;return response(url.endsWith('cart.js')?{items:[]}:{...certificate,properties:{_sports_cave_frame_request:'other'}});};
 await assert.rejects(transfer('signed',{fetch,origin}),/handoff unavailable/);assert.equal(adds,0);
});
test('return links retain the exact product variant and anchor',()=>{
 assert.equal(targetPath('/products/art?variant=42#sizes',origin),'/products/art?variant=42&sc_cart=1#sizes');
 assert.equal(targetPath('/en-us/account',origin),'/collections/all-sports-wall-art?sc_cart=1');
});
