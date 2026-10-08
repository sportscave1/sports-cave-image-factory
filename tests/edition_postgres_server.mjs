// Disposable SQL only, no production connections. Same PGlite test dependency.
import {PGlite} from './fixtures/crm/node_modules/@electric-sql/pglite/dist/index.js';
import {readFileSync} from 'node:fs';
import http from 'node:http';
const db=new PGlite();
await db.exec(readFileSync('tests/fixtures/edition_base.sql','utf8'));
for(const f of ['create_edition_runs_phase2.sql','20260825_atomic_edition_allocation_ledger.sql','20260912045939_independent_edition_cursor.sql','20261008041452_edition_version_transitions.sql','20261008045733_edition_version_guard_hardening.sql','20261008065000_explicit_edition_cursor_override.sql'])
 await db.exec(readFileSync('migrations/'+f,'utf8').replace('CREATE EXTENSION IF NOT EXISTS pgcrypto;',''));
let queue=Promise.resolve();
http.createServer(async(req,res)=>{let body='';for await(const chunk of req)body+=chunk;
 queue=queue.then(async()=>{try{const {sql,args=[]}=JSON.parse(body);const result=await db.query(sql,args);res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(result));}
 catch(e){res.writeHead(400,{'Content-Type':'application/json'});res.end(JSON.stringify({error:e.message}));}});
}).listen(8874,'127.0.0.1',()=>console.log('Disposable Edition SQL ready on 8874'));
