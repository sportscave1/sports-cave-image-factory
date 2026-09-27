// Local-only PostgreSQL fixture. Never connects to Supabase.
import {PGlite} from './fixtures/crm/node_modules/@electric-sql/pglite/dist/index.js';
import {readFileSync} from 'node:fs';
import http from 'node:http';
const db=new PGlite();
await db.exec('CREATE ROLE anon; CREATE ROLE authenticated;');
await db.exec(readFileSync('migrations/20260927093818_crm_marketing_v1.sql','utf8').replace('CREATE EXTENSION IF NOT EXISTS pgcrypto;',''));
await db.exec(`CREATE TABLE edition_orders(id bigserial primary key,shopify_customer_id text,customer_email text,edition_number int,edition_total int,product_title text,variant_title text,certificate_file_url text,shopify_order_name text);`);
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
