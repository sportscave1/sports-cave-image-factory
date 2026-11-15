import test from 'node:test';
import assert from 'node:assert/strict';
import {loadCollectionOrders} from './collection-order-pages.js';
import {collectCertificates} from './legacy-certificate-utils.js';

function response(id, nodes, hasNextPage = false, endCursor = null) {
  return {ok: true, json: async () => ({data: {customer: {id, orders: {nodes, pageInfo: {hasNextPage, endCursor}}}}})};
}

test('finds certificates beyond the first fifty authenticated orders', async () => {
  let count = 0;
  const fetchPage = async (url, options) => {
    assert.equal(url, 'shopify://customer-account/api/2026-04/graphql.json');
    assert.deepEqual(JSON.parse(options.body).variables, {after: count ? 'page-two' : null});
    return count++ ? response('customer-A', [{id:'order-51', name:'#51', metafield:{jsonValue:[{certificate_id:'fixture',shopify_customer_id:'customer-A',shopify_order_id:'order-51'}]}}]) :
      response('customer-A', Array.from({length:50},(_,i)=>({id:'order-'+i})), true, 'page-two');
  };
  const result = await loadCollectionOrders(fetchPage,'2026-04','fixture');
  assert.equal(result.orders.length,51);
  assert.equal(collectCertificates(result.orders,result.customer).length,1);
});

test('rejects changing customer identity between pages', async () => {
  let n = 0;
  await assert.rejects(loadCollectionOrders(async()=>n++ ? response('B',[]) : response('A',[],true,'next'),'2026-04','fixture'),/session changed/);
});

test('rejects repeated cursor, missing customer and incomplete authority', async () => {
  await assert.rejects(loadCollectionOrders(async()=>response('A',[],true,'same'),'2026-04','fixture'),/pagination/);
  await assert.rejects(loadCollectionOrders(async()=>response(null,[]),'2026-04','fixture'),/session/);
  await assert.rejects(loadCollectionOrders(async()=>({ok:true,json:async()=>({data:{customer:{id:'A',orders:{nodes:[]}}}})}),'2026-04','fixture'),/incomplete/);
});

test('does not turn permission failures into an empty collection', async () => {
  await assert.rejects(loadCollectionOrders(async()=>({ok:true,json:async()=>({errors:[{message:'Denied'}]})}),'2026-04','fixture'),/query failed/);
});

test('caps history requests and rejects duplicate orders', async () => {
  let n=0;
  await assert.rejects(loadCollectionOrders(async()=>response('A',[],true,String(++n)),'2026-04','fixture'),/limit/);
  assert.equal(n,20);
  await assert.rejects(loadCollectionOrders(async()=>response('A',[{id:'same'},{id:'same'}]),'2026-04','fixture'),/history changed/);
});

test('another customer certificate in an owned order is filtered', async () => {
  const order={id:'order-A',name:'#A',metafield:{jsonValue:[{certificate_id:'B',shopify_customer_id:'customer-B',shopify_order_id:'order-A'}]}};
  const result=await loadCollectionOrders(async()=>response('customer-A',[order]),'2026-04','fixture');
  assert.deepEqual(collectCertificates(result.orders,result.customer),[]);
});

test('pending and missing records never invent a download or allocation', async () => {
  const pending={certificate_id:'pending',shopify_customer_id:'A',shopify_order_id:'one'};
  const result=await loadCollectionOrders(async()=>response('A',[
    {id:'one',name:'#1',metafield:{jsonValue:[pending]}}, {id:'two',name:'#2'}
  ]),'2026-04','fixture');
  const rows=collectCertificates(result.orders,result.customer);
  assert.equal(rows.length,1);
  assert.equal(rows[0].certificate_pdf_url,'');
  assert.equal(rows[0].edition_display,'');
  assert.deepEqual(pending,{certificate_id:'pending',shopify_customer_id:'A',shopify_order_id:'one'});
});

test('wrong order records are excluded and a fresh retry recovers from transport error', async () => {
  await assert.rejects(loadCollectionOrders(async()=>{throw new Error('timeout');},'2026-04','fixture'),/timeout/);
  const result=await loadCollectionOrders(async()=>response('A',[
    {id:'one',name:'#1',metafield:{jsonValue:[{certificate_id:'wrong',shopify_customer_id:'A',shopify_order_id:'two'}]}}
  ]),'2026-04','fixture');
  assert.deepEqual(collectCertificates(result.orders,result.customer),[]);
});
