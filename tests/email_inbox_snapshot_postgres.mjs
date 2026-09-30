// Execute the actual private snapshot migration/queries locally. No cloud writes.
import {PGlite} from '../output/email-idle-pg/node_modules/@electric-sql/pglite/dist/index.js';
import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const python=`import ast,json
tree=ast.parse(open('support_email_snapshot.py').read())
out={}
for node in ast.walk(tree):
 if isinstance(node,ast.FunctionDef):
  out[node.name]=[call.args[0].value for call in ast.walk(node) if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute) and call.func.attr=='execute' and isinstance(call.args[0],ast.Constant)]
print(json.dumps(out))`;
const queries=JSON.parse(execFileSync('.venv/Scripts/python.exe',['-c',python],{encoding:'utf8'}));
const db=new PGlite();
await db.exec('CREATE ROLE anon; CREATE ROLE authenticated;');
const migration=readFileSync('migrations/20260930055619_support_email_inbox_snapshot.sql','utf8');
await db.exec(migration);await db.exec(migration);
const query=(name,args)=>{let n=0;return db.query(queries[name][0].replace(/%s/g,()=>'$'+(++n)),args);};
await query('save_index',['scope',JSON.stringify({synced_at:20,snapshot:{messages:[{uid:'8'}]}}),20]);
await query('save_index',['scope',JSON.stringify({synced_at:10,snapshot:{messages:[]}}),10]);
assert.equal((await query('read_index',['scope'])).rows[0].snapshot.snapshot.messages[0].uid,'8');
assert.equal((await query('read_index',['another-scope'])).rows.length,0);
for(const role of ['anon','authenticated']){
 await db.exec('SET ROLE '+role);
 await assert.rejects(()=>db.query('SELECT * FROM support_email_inbox_snapshot'),/permission denied/);
 await db.exec('RESET ROLE');
}
assert.equal((await db.query("SELECT relrowsecurity FROM pg_class WHERE relname='support_email_inbox_snapshot'")).rows[0].relrowsecurity,true);
await db.close();console.log('Snapshot SQL: idempotent migration, timestamp fencing, scope isolation and private RLS passed.');
