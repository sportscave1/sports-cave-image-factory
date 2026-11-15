// Actual production candidate SQL executed in disposable PostgreSQL; no mocks.
import {PGlite} from '../.tmp-preview-performance/pg/node_modules/@electric-sql/pglite/dist/index.js';
import fs from 'node:fs';import assert from 'node:assert/strict';
const queries=JSON.parse(fs.readFileSync('.tmp-preview-performance/queries.json','utf8'));
const baseline=JSON.parse(fs.readFileSync('.tmp-preview-performance/before-queries.json','utf8'));
const db=new PGlite();
await db.exec(`CREATE TABLE crm_lifecycle_customers(customer_id text PRIMARY KEY,name text,email text,recipient_hash text,consent text,profile jsonb,verified_at timestamptz,subscribed_at timestamptz);
CREATE TABLE shopify_orders(shopify_order_id text PRIMARY KEY,shopify_customer_id text,customer_id text,created_at timestamptz,financial_status text,fulfillment_status text,cancelled_at timestamptz,raw_json jsonb);
CREATE TABLE crm_webhook_events(provider text,topic text,object_id text,occurred_at timestamptz);
CREATE TABLE crm_suppressions(shopify_customer_id text,recipient_hash text);
CREATE INDEX crm_lifecycle_subscribed ON crm_lifecycle_customers(subscribed_at DESC,customer_id);
CREATE INDEX lifecycle_order_events ON crm_webhook_events(object_id,topic,occurred_at) WHERE provider='shopify';
CREATE INDEX order_customer ON shopify_orders(shopify_customer_id);
CREATE INDEX crm_lifecycle_order_customer_date ON shopify_orders((COALESCE(NULLIF(shopify_customer_id,''),customer_id)),created_at DESC) WHERE upper(financial_status) IN ('PAID','PARTIALLY_REFUNDED') AND cancelled_at IS NULL;
CREATE INDEX suppression_customer ON crm_suppressions(shopify_customer_id);
INSERT INTO crm_lifecycle_customers SELECT 'gid://shopify/Customer/'||i,'Fixture '||i,'fixture'||i||'@example.invalid','hash'||i,'SUBSCRIBED',jsonb_build_object('id','gid://shopify/Customer/'||i,'firstName','Fixture '||i),now(),now()-interval '1 day'*i FROM generate_series(1,1000) i;
INSERT INTO shopify_orders SELECT 'gid://shopify/Order/'||i,'gid://shopify/Customer/'||i,NULL,now()-interval '1 day'*i,'PAID','FULFILLED',NULL,jsonb_build_object('lineItems',jsonb_build_object('nodes','[]'::jsonb,'pageInfo',jsonb_build_object('hasNextPage',false))) FROM generate_series(1,800) i;
INSERT INTO crm_webhook_events SELECT 'shopify','orders/paid',shopify_order_id,created_at FROM shopify_orders;
INSERT INTO crm_webhook_events SELECT 'shopify','orders/fulfilled',shopify_order_id,created_at+interval '2 days' FROM shopify_orders;
INSERT INTO crm_webhook_events SELECT 'shopify','products/update','unrelated'||i,now() FROM generate_series(1,10000) i;
INSERT INTO crm_suppressions VALUES ('gid://shopify/Customer/1','hash1');
UPDATE shopify_orders SET financial_status='REFUNDED' WHERE shopify_order_id='gid://shopify/Order/2';
UPDATE shopify_orders SET fulfillment_status='UNFULFILLED' WHERE shopify_order_id='gid://shopify/Order/3';
UPDATE crm_lifecycle_customers SET consent='UNSUBSCRIBED' WHERE customer_id='gid://shopify/Customer/4';
ANALYZE;`);
const param=sql=>{let n=0;return sql.replace(/%s/g,()=>'$'+(++n))};
const results={dataset:'1000 synthetic customers; 800 orders; 11600 events; PGlite actual PostgreSQL',flows:{}};
try{
 for(const [kind,query]of Object.entries(queries)){
  const at=performance.now(),before=await db.query(param(baseline[kind].sql),baseline[kind].args);const oldMs=performance.now()-at;
  const start=performance.now(),after=await db.query(param(query.sql),query.args);const cold=performance.now()-start;
  const t=performance.now();await db.query(param(query.sql),query.args);const warm=performance.now()-t;
  assert.ok(after.rows.length>0,kind);assert.ok(!after.rows.some(r=>['gid://shopify/Customer/1','gid://shopify/Customer/4'].includes(r.customer_id)),kind+' suppression/consent');
  if(kind==='welcome')assert.equal(after.rows[0].customer_id,'gid://shopify/Customer/2'); // Refunded order is not a qualifying purchase.
  if(kind==='post_purchase')assert.equal(after.rows[0].key,'gid://shopify/Order/3');
  if(kind==='fulfilled')assert.equal(after.rows[0].key,'gid://shopify/Order/5');
  if(kind==='win_back')assert.ok(new Date(after.rows[0].paid_at)<=new Date(query.args[0]));
  if(kind!=='welcome')assert.equal(after.rows[0].order_record.shopify_order_id,after.rows[0].key);
  results.flows[kind]={before_ms:oldMs,after_cold_ms:cold,after_warm_ms:warm,rows:after.rows.length};
 }
 fs.writeFileSync('.tmp-preview-performance/sql-results.json',JSON.stringify(results,null,2));
 console.log('PASS real SQL: four flows, paid/fulfilled ordering, consent/suppression, source associations and inactivity');console.log(JSON.stringify(results));
}finally{await db.close();}
