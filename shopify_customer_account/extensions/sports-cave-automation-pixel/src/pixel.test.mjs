import {test} from 'node:test';
import assert from 'node:assert/strict';
import {EVENTS,start} from './pixel.mjs';

function fixture(allowed=true) {
  const subscriptions={},calls=[];let change;
  start({analytics:{subscribe:(n,fn)=>{subscriptions[n]=fn;}},init:{customerPrivacy:{analyticsProcessingAllowed:allowed,marketingAllowed:allowed}},
    customerPrivacy:{subscribe:(_,fn)=>{change=fn;}},settings:{endpoint:'https://fixture.example/shopify/customer-events',shop:'fixture.myshopify.com',ingestionId:'a'.repeat(32)}},
    (url,body)=>{calls.push(JSON.parse(body.body));return Promise.resolve();});
  return {subscriptions,calls,change};
}

test('exact six standard subscriptions only',()=>{assert.deepEqual(Object.keys(fixture().subscriptions),EVENTS);});
for(const name of EVENTS) test(`${name}: minimal anonymous envelope`,()=>{
  const f=fixture();f.subscriptions[name]({id:'event-1',clientId:'client-1',timestamp:'2026-10-03T00:00:00Z',data:{customer:{email:'private@example.test'},productVariant:{product:{id:'123'}}}});
  assert.equal(f.calls.length,1);assert.equal(f.calls[0].event_name,name);
  assert.equal(f.calls[0].product_id,'gid://shopify/Product/123');
  assert.ok(!JSON.stringify(f.calls).includes('private'));assert.ok(!('customer_id' in f.calls[0]));
});
test('consent controls collection and later revocation',()=>{
  const f=fixture(false),event={id:'e',clientId:'c',timestamp:'2026-10-03T00:00:00Z'};
  f.subscriptions.product_viewed(event);assert.equal(f.calls.length,0);
  f.change({customerPrivacy:{analyticsProcessingAllowed:true,marketingAllowed:true}});f.subscriptions.product_viewed(event);assert.equal(f.calls.length,1);
  f.change({customerPrivacy:{analyticsProcessingAllowed:true,marketingAllowed:false}});f.subscriptions.product_viewed(event);assert.equal(f.calls.length,1);
});
