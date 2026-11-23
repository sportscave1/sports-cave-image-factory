import assert from 'node:assert/strict';
import test from 'node:test';
import {collectionThumbnail} from '../shopify_customer_account/extensions/customer-certificate-vault/src/collection-image-utils.js';
import {pairedProducts, UPSELL_QUERY} from '../shopify_customer_account/extensions/customer-certificate-vault/src/account-commerce.js';
test('product cards retain smart rank and product-wide availability without fetching variants',()=>{
 const nodes=[{id:'c',handle:'c',availableForSale:true},{id:'a',handle:'a',availableForSale:false},{id:'b',handle:'b',availableForSale:true},null];
 assert.deepEqual(pairedProducts(['a','b','c','b'],nodes).map(p=>p.id),['b','c']);
 assert.doesNotMatch(UPSELL_QUERY,/\bvariants\s*\(/);
 assert.match(UPSELL_QUERY,/availableForSale/);
 assert.match(UPSELL_QUERY,/maxWidth: 400/);
 assert.match(UPSELL_QUERY,/@inContext\(country: \$country\)/);
});
test('thumbnail keeps identity version and format while requesting bounded pixels',()=>{
 const original='https://cdn.shopify.com/s/files/1/2/files/black-frame.webp?v=123';
 const thumb=new URL(collectionThumbnail(original));
 assert.equal(thumb.pathname,new URL(original).pathname);
 assert.equal(thumb.searchParams.get('v'),'123');assert.equal(thumb.searchParams.get('width'),'320');
 assert.equal(new URL(collectionThumbnail(original+'&width=100')).searchParams.get('width'),'100');
 assert.equal(collectionThumbnail(original,99999),original);
});
test('signed downloads, non-Shopify sources and certificate URLs are untouched',()=>{
 for(const value of ['https://example.test/certificate.jpg?token=private','https://cdn.shopify.com/s/files/1/2/files/image.jpg?signature=private','https://cdn.shopify.com.evil.test/s/files/x.jpg','https://sports-cave-image-factory.onrender.com/api/collector-vault/asset?token=owned','not-a-url'])assert.equal(collectionThumbnail(value),value);
 assert.equal(collectionThumbnail(''),'');
});
