import {test} from 'node:test';
import assert from 'node:assert/strict';
import {accountCountry,compactTitle,comparePrice,marketFrames,UPSELL_QUERY,FRAME_PRICE_QUERY} from './account-commerce.js';
test('account market comes from live country signal',()=>{
 const signal={value:{isoCode:'US'}};const api={localization:{country:signal}};
 assert.equal(accountCountry(api),'US');signal.value={isoCode:'GB'};assert.equal(accountCountry(api),'GB');assert.equal(accountCountry({}),'AU');
});
test('compact display title preserves actual product names',()=>{
 assert.equal(compactTitle('The Captain – Derek Jeter Wall Art'),'The Captain – Derek Jeter');
 assert.equal(compactTitle('WALL ART   — Edition'),'— Edition');
});
test('RRP is shown only for genuine higher compare-at price in the same currency',()=>{
 const variant={price:{amount:'90',currencyCode:'USD'},compareAtPrice:{amount:'120',currencyCode:'USD'}};
 assert.equal(comparePrice(variant),variant.compareAtPrice);variant.compareAtPrice.currencyCode='AUD';assert.equal(comparePrice(variant),null);
 variant.compareAtPrice={amount:'80',currencyCode:'USD'};assert.equal(comparePrice(variant),null);
});
test('framing uses matching published variants and contextual currency',()=>{
 const product={product_id:'p',variants:[{variant_id:'black',color:'Black'},{variant_id:'oak',color:'Oak'}]};
 const result=marketFrames(product,{id:'p',variants:{nodes:[{id:'black',availableForSale:true,price:{amount:'65',currencyCode:'USD'}},{id:'oak',availableForSale:false}]}});
 assert.equal(result.variants.length,1);assert.equal(result.contextual_price.currencyCode,'USD');
 assert.throws(()=>marketFrames(product,{id:'other'}));
 assert.ok(UPSELL_QUERY.includes('@inContext(country: $country)'));assert.ok(FRAME_PRICE_QUERY.includes('@inContext(country: $country)'));
});
