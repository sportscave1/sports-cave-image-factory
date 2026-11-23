import assert from 'node:assert/strict';
import test from 'node:test';
import {secondProductImage,reviewProductId,REVIEW_IMAGE_QUERY} from '../shopify_customer_account/extensions/customer-certificate-vault/src/account-review-utils.js';
test('setup uses exactly second ordered product image with lightweight CDN transform',()=>{
 const second={url:'https://cdn.shopify.com/second.jpg',altText:'Lifestyle'};
 assert.equal(secondProductImage({images:{nodes:[{url:'https://cdn.shopify.com/first.jpg'},second]}}),second);
 assert.equal(secondProductImage({images:{nodes:[second]}}),null);
 assert.equal(secondProductImage({images:{nodes:[second,{url:'javascript:bad'}]}}),null);
 assert.match(REVIEW_IMAGE_QUERY,/first: 2/); assert.match(REVIEW_IMAGE_QUERY,/maxWidth: 640/);
});
test('review image follows authorized review product instead of carousel selection',()=>{
 assert.equal(reviewProductId({shopify_product_id:'reviewed'}, {shopify_product_id:'other'}),'reviewed');
 assert.equal(reviewProductId(null,{shopify_product_id:'fallback'}),'fallback');
});
