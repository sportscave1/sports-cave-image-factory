// Disposable loopback-only PostgreSQL. No production connection or credentials.
import {PGlite} from './fixtures/crm/node_modules/@electric-sql/pglite/dist/index.js';
import {readFileSync} from 'node:fs';
import http from 'node:http';
const db=new PGlite();
await db.exec('CREATE ROLE anon; CREATE ROLE authenticated;');
const migration=readFileSync('migrations/20261006063028_support_email_durable_delivery.sql','utf8');
await db.exec(migration);await db.exec(migration); // Additive and idempotent.
let queue=Promise.resolve();
const server=http.createServer(async(req,res)=>{
 if(req.method!=='POST'){res.writeHead(405).end();return;}
 let body='';for await(const part of req)body+=part;
 const run=async()=>{try{
   const {sql,args=[]}=JSON.parse(body),result=await db.query(sql,args);
   res.writeHead(200,{'content-type':'application/json'}).end(JSON.stringify(result));
 }catch(error){res.writeHead(400).end(JSON.stringify({error:error.message}));}};
 queue=queue.then(run,run);
});
server.listen(8879,'127.0.0.1',()=>console.log('Email PostgreSQL fixture ready on 8879'));
process.on('SIGTERM',()=>server.close(()=>db.close()));
