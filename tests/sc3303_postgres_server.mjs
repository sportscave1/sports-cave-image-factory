// Disposable loopback SQL with synthetic data only. Never loads credentials.
import {PGlite} from './fixtures/crm/node_modules/@electric-sql/pglite/dist/index.js';
import {readFileSync} from 'node:fs';
import http from 'node:http';
process.on('uncaughtException',e=>{console.error(e.message);process.exit(1);});
const db=new PGlite();
await db.exec(readFileSync('tests/fixtures/edition_base.sql','utf8'));
for(const f of ['create_edition_runs_phase2.sql','20260825_atomic_edition_allocation_ledger.sql','20260912045939_independent_edition_cursor.sql','20261008041452_edition_version_transitions.sql','20261008045733_edition_version_guard_hardening.sql','20261008065000_explicit_edition_cursor_override.sql','20261008090000_edition_admin_cursor_repair.sql'])
  await db.exec(readFileSync('migrations/'+f,'utf8').replace('CREATE EXTENSION IF NOT EXISTS pgcrypto;',''));
await db.exec(`
ALTER TABLE shopify_orders ADD COLUMN order_name text, ADD COLUMN fulfillment_status text DEFAULT 'UNFULFILLED',
  ADD COLUMN cancelled_at timestamptz, ADD COLUMN total_price text, ADD COLUMN raw jsonb DEFAULT '{}', ADD COLUMN updated_at timestamptz;
ALTER TABLE edition_orders ADD COLUMN certificate_id text, ADD COLUMN certificate_file_url text, ADD COLUMN shopify_file_id text,
  ADD COLUMN certificate_r2_key text, ADD COLUMN certificate_preview_r2_key text;
ALTER TABLE certificates ADD COLUMN shopify_order_id text, ADD COLUMN shopify_order_name text, ADD COLUMN shopify_handle text,
  ADD COLUMN product_handle text, ADD COLUMN shopify_product_id text, ADD COLUMN edition_number int;
CREATE TABLE shopify_order_lines(id bigserial PRIMARY KEY,shopify_order_id text,shopify_line_item_id text,
  shopify_product_id text,quantity int,assignment_status text,last_error text,updated_at timestamptz);
CREATE TABLE edition_order_sync_locks(canonical_order_key text PRIMARY KEY,shopify_order_id text,shopify_order_name text,
  status text,reason text,created_at timestamptz DEFAULT now(),updated_at timestamptz DEFAULT now());
CREATE TABLE prodigi_dispatch_rows(row_id text PRIMARY KEY,shopify_order_id text,shopify_order_name text,shopify_line_item_id text);
CREATE TABLE auto_edition_jobs(id text PRIMARY KEY,payload jsonb);
CREATE TABLE webhook_events(webhook_id text PRIMARY KEY,shopify_order_id text,shopify_order_name text,payload jsonb,status text);
CREATE TABLE IF NOT EXISTS edition_repair_audits(repair_key text PRIMARY KEY,product_gid text,mode text,snapshot_sha256 text,report jsonb,
  actor text,applied_at timestamptz);
CREATE TABLE IF NOT EXISTS edition_repair_archive(repair_key text,edition_order_id text,row_snapshot jsonb,PRIMARY KEY(repair_key,edition_order_id));
`);
await db.exec(readFileSync('scripts/sc3303_cancellation_guards.sql','utf8'));
let queue=Promise.resolve();
http.createServer(async(req,res)=>{let body='';for await(const chunk of req)body+=chunk;
  queue=queue.then(async()=>{try{const {sql,args=[]}=JSON.parse(body);const result=await db.query(sql,args);
    res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(result));}
    catch(e){res.writeHead(400,{'Content-Type':'application/json'});res.end(JSON.stringify({error:e.message}));}});
}).listen(8874,'127.0.0.1',()=>console.log('Disposable SC3303 SQL ready on 8874'));
