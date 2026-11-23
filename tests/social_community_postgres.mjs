// Disposable in-memory PostgreSQL fixture. No application or provider runtime.
import {PGlite} from './fixtures/crm/node_modules/@electric-sql/pglite/dist/index.js';
import {readFileSync} from 'node:fs';
import http from 'node:http';
const db = new PGlite();
await db.exec("CREATE ROLE anon; CREATE ROLE authenticated;");
await db.exec(readFileSync('scripts/social_community_schema.sql','utf8'));
let queue = Promise.resolve();
http.createServer(async (req,res) => {
  if (req.method !== 'POST') {res.writeHead(405).end();return;}
  let body='';for await (const part of req) body+=part;
  const run=async()=>{try {
    const {sql,args=[]}=JSON.parse(body);
    const result=await db.query(sql,args);
    res.writeHead(200,{'content-type':'application/json'}).end(JSON.stringify(result));
  } catch(error) {
    res.writeHead(400,{'content-type':'application/json'}).end(JSON.stringify({error:error.message}));
  }};
  queue=queue.then(run,run);
}).listen(Number(process.argv[2]),'127.0.0.1',()=>console.log('ready'));
