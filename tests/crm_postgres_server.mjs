// Local-only PostgreSQL fixture. Never connects to Supabase.
import {PGlite} from './fixtures/crm/node_modules/@electric-sql/pglite/dist/index.js';
import {readFileSync} from 'node:fs';
import http from 'node:http';
const db=new PGlite();
await db.exec('CREATE ROLE anon; CREATE ROLE authenticated;');
await db.exec(readFileSync('migrations/20260927093818_crm_marketing_v1.sql','utf8').replace('CREATE EXTENSION IF NOT EXISTS pgcrypto;',''));
await db.exec(readFileSync('migrations/20260928020740_crm_campaign_workspace_v1.sql','utf8'));
await db.exec(readFileSync('migrations/20260928024722_crm_campaigns_first_workspace.sql','utf8'));
await db.exec(readFileSync('migrations/20260930031755_crm_campaigns_production_v2.sql','utf8'));
await db.exec(readFileSync('migrations/20260930051803_crm_email_attribution_hardening.sql','utf8'));
await db.exec(readFileSync('migrations/20261002132200_crm_native_automations_v1.sql','utf8'));
await db.exec(readFileSync('migrations/20261002143522_crm_shopify_automation_triggers_v1.sql','utf8'));
await db.exec(readFileSync('migrations/20261002152512_reviews_v1.sql','utf8'));
await db.exec(readFileSync('migrations/20261005145500_crm_automation_reporting_indexes.sql','utf8'));
await db.exec(`CREATE TABLE edition_orders(id bigserial primary key,shopify_customer_id text,customer_email text,edition_number int,edition_total int,product_title text,variant_title text,certificate_file_url text,shopify_order_name text);`);
await db.exec(readFileSync('migrations/20261005061015_crm_automation_publication_jobs.sql','utf8'));
await db.exec(readFileSync('migrations/20261005064444_crm_checkout_analytics.sql','utf8'));
await db.exec(readFileSync('migrations/20261006033000_crm_single_delay.sql','utf8'));
await db.exec(readFileSync('migrations/20261010090000_crm_flow_tests.sql','utf8'));
await db.exec(readFileSync('migrations/20261010110000_crm_campaign_preparation.sql','utf8'));
let queue=Promise.resolve();
const server=http.createServer(async(req,res)=>{
 if(req.method!=='POST'){res.writeHead(405).end();return;}
 let body='';for await(const part of req)body+=part;
 const run=async()=>{
  try { const {sql,args=[]}=JSON.parse(body);const r=await db.query(sql,args);res.writeHead(200,{'content-type':'application/json'}).end(JSON.stringify({rows:r.rows,fields:r.fields})); }
  catch(e){res.writeHead(400,{'content-type':'application/json'}).end(JSON.stringify({error:String(e.message)}));}
 };
 queue=queue.then(run,run);
});
server.listen(Number(process.env.CRM_FIXTURE_SQL_PORT||8873),'127.0.0.1',()=>console.log('CRM fixture PostgreSQL ready on loopback'));
process.on('SIGTERM',()=>server.close(()=>db.close()));
