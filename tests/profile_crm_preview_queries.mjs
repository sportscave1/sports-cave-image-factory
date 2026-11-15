// Actual PostgreSQL plans over the existing synthetic SQL fixture; no cloud DB.
import {PGlite} from '../.tmp-preview-performance/pg/node_modules/@electric-sql/pglite/dist/index.js';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const db=new PGlite();
const setup=fs.readFileSync('tests/test_crm_preview_queries.mjs','utf8').match(/await db.exec\(`([\s\S]*?)`\);/)[1];
await db.exec(setup);
await db.exec("INSERT INTO shopify_orders(shopify_order_id,financial_status,created_at) VALUES('unowned-null-customer','PAID',now())");
const versions=Object.fromEntries(['before','after'].map(v=>[v,JSON.parse(fs.readFileSync('.tmp-preview-ultimate/'+(v==='before'?'before-queries':'queries')+'.json','utf8'))]));
const stats=xs=>{xs.sort((a,b)=>a-b);return {median:xs[Math.floor(xs.length/2)],p95:xs[Math.ceil(xs.length*.95)-1]}};
const results={source:'PGlite PostgreSQL; 1000 synthetic subscribers, 800 orders, 11600 events. Existing indexes. Not production query plans.',flows:{}};
try{for(const [version,queries] of Object.entries(versions))for(const [kind,q] of Object.entries(queries)){
 let n=0;const sql=q.sql.replace(/%s/g,()=>'$'+(++n));
 const plan=(await db.query('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+sql,q.args)).rows[0]['QUERY PLAN'];
 const rows=(await db.query(sql,q.args)).rows;
 assert.ok(rows.length>0);if(kind==='welcome')assert.equal(rows[0].customer_id,'gid://shopify/Customer/2');
 const samples=[];for(let i=0;i<20;i++){const t=performance.now();await db.query(sql,q.args);samples.push(performance.now()-t)}
 results.flows[version+'_'+kind]={...stats(samples),plan};
}fs.writeFileSync('.tmp-preview-ultimate/query-plans.json',JSON.stringify(results,null,2));
 console.log(JSON.stringify(Object.fromEntries(Object.entries(results.flows).map(([k,v])=>[k,{median:v.median,p95:v.p95,execution_ms:v.plan[0]['Execution Time']}]))));
}finally{await db.close()}
