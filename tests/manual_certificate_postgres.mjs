// Isolated real PostgreSQL trigger regression tests; no production connections.
// Set PGLITE_MODULE to an installed @electric-sql/pglite/dist/index.js.
import {pathToFileURL} from 'node:url';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const {PGlite}=await import(pathToFileURL(process.env.PGLITE_MODULE).href);
const db=new PGlite();
await db.exec(`
CREATE ROLE anon; CREATE ROLE authenticated;
CREATE TABLE os_users(id uuid primary key,role text,is_active boolean,account_status text,email text,display_name text,username text);
CREATE TABLE shopify_orders(shopify_order_id text primary key,order_name text,shopify_order_name text,raw_json jsonb,fulfillment_status text);
CREATE TABLE shopify_order_lines(id serial,shopify_order_id text,shopify_line_item_id text,shopify_product_id text,product_title text,assignment_status text,last_error text,raw_json jsonb);
CREATE TABLE edition_products(id serial,shopify_product_gid text,shopify_product_id text,shopify_handle text,product_title text,active_edition_run_id uuid,edition_total int,sold_count int,remaining_count int,next_edition_number int,sold_out boolean,is_sold_out boolean,active boolean,is_active boolean,edition_status text);
CREATE TABLE edition_runs(id uuid,edition_total int,status text);
CREATE TABLE edition_orders(id serial,allocation_valid boolean,edition_number int,edition_total int,source_channel text,external_order_id text,external_line_item_id text,shopify_line_item_id text,shopify_product_id text,shopify_handle text);
CREATE TABLE prodigi_dispatch_rows(shopify_line_item_id text,prodigi_status text);
CREATE TABLE certificates(edition_order_id text,shopify_order_id text,shopify_line_item_id text);
`);
for(const name of ['20260828_manual_expired_order_line_editions.sql','20260829_fix_manual_expired_edition_identity.sql','20260912224424_manual_certificate_controls.sql'])
 await db.exec(readFileSync(new URL('../migrations/'+name,import.meta.url),'utf8'));
const actor='00000000-0000-0000-0000-000000000001';
await db.exec(`
INSERT INTO os_users VALUES('${actor}','admin',true,'active','operator@example.test','Operator','operator');
INSERT INTO edition_runs VALUES('${actor}',100,'sold_out');
INSERT INTO edition_products(shopify_product_gid,shopify_handle,product_title,active_edition_run_id,edition_total,sold_count,remaining_count,next_edition_number,sold_out,active) VALUES('gid://shopify/Product/3','wall-art','Wall Art','${actor}',100,100,0,101,true,false);
INSERT INTO shopify_orders VALUES('gid://shopify/Order/1','#SC3150','#SC3150','{}','');
INSERT INTO shopify_order_lines(shopify_order_id,shopify_line_item_id,shopify_product_id,product_title,assignment_status,last_error,raw_json) VALUES('gid://shopify/Order/1','gid://shopify/LineItem/2','gid://shopify/Product/3','Wall Art','Error','Edition limit reached','{}');
INSERT INTO edition_orders VALUES(1,true,100,100,'shopify','old','old','old','gid://shopify/Product/3','wall-art');
`);
const baseline=JSON.stringify((await db.query('SELECT * FROM edition_products')).rows);
const ledger=JSON.stringify((await db.query('SELECT * FROM edition_orders')).rows);
async function save(number=100,confirmed=false){return (await db.query(`
INSERT INTO manual_order_line_editions(source_channel,external_order_id,external_line_item_id,canonical_product_gid,
edition_number,edition_total,reason,created_by_user_id,created_by_email,created_by_display_name,verified_order_name,
verified_product_title,verified_assignment_status,verified_last_error,verified_series_status,verified_sold_count,
verified_remaining_count,verified_next_edition_number,duplicate_confirmed)
VALUES('shopify','gid://shopify/Order/1','gid://shopify/LineItem/2','gid://shopify/Product/3',$1,100,'Exception',$2,'','','','','','','',0,0,0,$3)
ON CONFLICT(source_channel,external_order_id,external_line_item_id) DO UPDATE SET edition_number=EXCLUDED.edition_number,
reason=EXCLUDED.reason,duplicate_confirmed=EXCLUDED.duplicate_confirmed,created_by_user_id=EXCLUDED.created_by_user_id RETURNING *`,[number,actor,confirmed])).rows[0];}
let passed=0;
async function test(name,fn){await fn();passed++;console.log('PASS '+name);}
await test('duplicate history requires confirmation',()=>assert.rejects(save(),/Confirm the duplicate/));
let record;
await test('confirmed duplicate accepted without allocation',async()=>{record=await save(100,true);assert.equal(record.edition_number,100);});
await test('edit retains identity and old audited number',async()=>{const edited=await save(99);assert.equal(edited.id,record.id);const a=(await db.query("SELECT old_value,new_value FROM manual_certificate_audit WHERE action='UPDATE'")).rows[0];assert.equal(a.old_value.edition_number,100);assert.equal(a.new_value.edition_number,99);});
await test('audit cannot be rewritten',()=>assert.rejects(db.exec("UPDATE manual_certificate_audit SET action='hidden'"),/immutable/));
await test('removal requires administrator',()=>assert.rejects(db.exec('DELETE FROM manual_order_line_editions'),/administrator/));
await db.query("SELECT set_config('sports_cave.manual_certificate_actor',$1,false)",[actor]);
await test('remove preserves audit and restores no override',async()=>{await db.exec('DELETE FROM manual_order_line_editions');assert.equal((await db.query('SELECT * FROM manual_order_line_editions')).rows.length,0);assert.equal((await db.query("SELECT * FROM manual_certificate_audit WHERE action='DELETE'")).rows.length,1);});
record=await save(100,true);
await db.query('INSERT INTO certificates VALUES($1,$2,$3)',['manual-edition:'+record.id,'gid://shopify/Order/1','gid://shopify/LineItem/2']);
await test('generated certificate locks edit',()=>assert.rejects(save(99),/certificate already exists/));
await test('generated certificate locks remove',()=>assert.rejects(db.exec('DELETE FROM manual_order_line_editions'),/certificate already exists/));
await test('all counters and history byte-for-byte unchanged',async()=>{assert.equal(JSON.stringify((await db.query('SELECT * FROM edition_products')).rows),baseline);assert.equal(JSON.stringify((await db.query('SELECT * FROM edition_orders')).rows),ledger);});
console.log(`${passed} PostgreSQL tests passed`);
await db.close();
