// Isolated localhost SQL fixture; never connects to production.
import {PGlite} from './fixtures/crm/node_modules/@electric-sql/pglite/dist/index.js';
import {readFileSync} from 'node:fs';
import http from 'node:http';
const db=new PGlite();
await db.exec('CREATE ROLE anon; CREATE ROLE authenticated;');
await db.exec("CREATE TABLE os_users(id uuid PRIMARY KEY,is_active boolean DEFAULT true,account_status text DEFAULT 'active',session_version integer DEFAULT 1)");
const migration=readFileSync('migrations/20261005092224_os_security_protection.sql','utf8');
await db.exec(migration);await db.exec(migration);
let queue=Promise.resolve();
const server=http.createServer(async(req,res)=>{
 let body='';for await(const part of req)body+=part;
 const run=async()=>{try{const {sql,args=[]}=JSON.parse(body);const r=await db.query(sql,args);res.writeHead(200,{'content-type':'application/json'}).end(JSON.stringify({rows:r.rows,fields:r.fields}));}catch(e){res.writeHead(400,{'content-type':'application/json'}).end(JSON.stringify({error:String(e.message)}));}};
 queue=queue.then(run,run);
});
server.listen(8873,'127.0.0.1',()=>console.log('Security PostgreSQL fixture ready'));
process.on('SIGTERM',()=>server.close(()=>db.close()));
