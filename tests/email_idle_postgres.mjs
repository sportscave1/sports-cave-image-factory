// Execute the production SQL with local PostgreSQL/PGlite. No cloud database.
import {PGlite} from '../output/email-idle-pg/node_modules/@electric-sql/pglite/dist/index.js';
import {execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
const python=`import ast,json
tree=ast.parse(open('support_email_idle_store.py').read())
out={}
for node in ast.walk(tree):
 if isinstance(node,ast.FunctionDef):
  out[node.name]=[call.args[0].value for call in ast.walk(node) if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute) and call.func.attr=='execute' and isinstance(call.args[0],ast.Constant)]
print(json.dumps(out))`;
const queries=JSON.parse(execFileSync('.venv/Scripts/python.exe',['-c',python],{encoding:'utf8'}));
const sql=(name,index=0)=>{let n=0;return queries[name][index].replace(/%s/g,()=>'$'+(++n));};
const db=new PGlite();
await db.exec("CREATE TABLE app_sync_state(key text primary key,value jsonb,status text,updated_at timestamptz)");
const query=(name,args,index=0)=>db.query(sql(name,index),args);
assert.equal((await query('claim',['lease','nathan-process'])).rows.length,1);
assert.equal((await query('claim',['lease','maria-process'])).rows.length,0);
assert.equal((await query('renew',['maria-process','lease','maria-process'])).rows.length,0);
assert.equal((await query('renew',['nathan-process','lease','nathan-process'])).rows.length,1);
assert.equal((await query('publish',['lease','maria-process'])).rows.length,0);
await db.exec('BEGIN');
assert.equal((await query('publish',['lease','nathan-process'])).rows.length,1);
const signal=(await query('publish',['signal',JSON.stringify({version:'v1',uidnext:8})],1)).rows[0].value;
assert.equal(signal.uidnext,8);assert.ok(signal.checked_at>0);
await db.exec('COMMIT');
assert.equal((await query('read',['signal'])).rows[0].value.version,'v1');
await query('release',['maria-process','lease','maria-process']);
assert.equal((await query('claim',['lease','replacement'])).rows.length,0);
await db.exec("UPDATE app_sync_state SET value=jsonb_set(value,'{until}','0') WHERE key='lease'");
assert.equal((await query('renew',['nathan-process','lease','nathan-process'])).rows.length,0);
assert.equal((await query('claim',['lease','replacement'])).rows.length,1);
assert.equal((await query('publish',['lease','nathan-process'])).rows.length,0);
await query('release',['replacement','lease','replacement']);
assert.equal((await query('claim',['lease','next'])).rows.length,1);
await db.close();console.log('Production lease/fencing/signal SQL passed on isolated PostgreSQL.');
