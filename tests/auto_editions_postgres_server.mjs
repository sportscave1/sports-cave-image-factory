// Disposable SQL engine for queue tests. No credentials or existing DB access.
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import http from 'node:http';
const {PGlite}=await import(pathToFileURL(process.env.AUTO_EDITIONS_TEST_PGLITE).href);
const db=new PGlite();
await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;');
await db.exec(readFileSync(new URL('../migrations/20261014004209_auto_editions_v6.sql',import.meta.url),'utf8'));
let queue=Promise.resolve();
const server=http.createServer(async(req,res)=>{
 let body='';for await(const chunk of req)body+=chunk;
 queue=queue.then(async()=>{
  try {const {sql,args=[]}=JSON.parse(body);const result=args.length?await db.query(sql,args):(await db.exec(sql)).at(-1);
   res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(result));
  } catch(error){res.writeHead(400,{'Content-Type':'application/json'});res.end(JSON.stringify({error:error.message}));}
 });
});
server.keepAliveTimeout=30000;
server.listen(0,'127.0.0.1',()=>console.log(server.address().port));
