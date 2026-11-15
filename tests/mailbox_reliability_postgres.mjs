// Existing PGlite test dependency, disposable memory DB, loopback only.
import {pathToFileURL} from 'node:url';
import {readFileSync} from 'node:fs';
import http from 'node:http';
const modulePath=process.env.MAILBOX_TEST_PGLITE;
if(!modulePath)throw new Error('Set MAILBOX_TEST_PGLITE to the existing PGlite dist/index.js');
const {PGlite}=await import(pathToFileURL(modulePath).href);
const db=new PGlite();await db.exec('CREATE ROLE anon; CREATE ROLE authenticated;');
await db.exec(readFileSync('migrations/20261006063028_support_email_durable_delivery.sql','utf8'));
let queue=Promise.resolve();
const server=http.createServer(async(req,res)=>{
 if(req.method!=='POST'){res.writeHead(405).end();return;}
 let body='';for await(const part of req)body+=part;
 const run=async()=>{try{const {sql,args=[]}=JSON.parse(body),result=await db.query(sql,args);res.writeHead(200,{'content-type':'application/json'}).end(JSON.stringify(result));}
 catch(e){res.writeHead(400).end(JSON.stringify({error:e.message}));}};
 queue=queue.then(run,run);
});
server.listen(8879,'127.0.0.1',()=>console.log('Disposable mailbox SQL fixture ready on 127.0.0.1:8879'));
process.on('SIGTERM',()=>server.close(()=>db.close()));
