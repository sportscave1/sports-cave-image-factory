// Real isolated PostgreSQL tests; no network or production connection.
import {pathToFileURL} from 'node:url';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
const {PGlite}=await import(pathToFileURL(process.env.PGLITE_MODULE).href);
let db=new PGlite();
await db.exec('CREATE ROLE anon; CREATE ROLE authenticated;');
for(const name of ['20260626_ads_intelligence_v1.sql','20260626_ads_intelligence_v2_breakdowns.sql','20260912235112_meta_review_reporting.sql'])
 await db.exec(readFileSync(new URL('../migrations/'+name,import.meta.url),'utf8'));
await db.exec(readFileSync(new URL('../migrations/20260912235112_meta_review_reporting.sql',import.meta.url),'utf8'));
console.log('PASS migration applies twice');
const commands=JSON.parse(execFileSync('.venv/Scripts/python.exe',['-m','tests.meta_review_sql_fixture'],{encoding:'utf8'}));
await db.exec("INSERT INTO ads_sync_logs(id,source) VALUES(1,'meta_review'); CREATE TABLE edition_guard(next_number int,sold int,remaining int); INSERT INTO edition_guard VALUES(101,100,0);");
async function sync(fail=false){
 await db.exec('BEGIN');
 try {
  for(const [index,command] of commands.entries()){
   let n=0; const sql=command.sql.replace(/%s/g,()=>'$'+(++n));
   await db.query(sql,command.params||[]);
   if(fail && index===commands.length-2) throw new Error('simulated failure before commit');
  }
  await db.exec('COMMIT');
 } catch(error){await db.exec('ROLLBACK'); throw error;}
}
await sync(); await sync();
assert.equal((await db.query('SELECT count(*) AS n FROM meta_ad_insights_daily')).rows[0].n,1);
console.log('PASS actual repository SQL and duplicate sync');
let row=(await db.query('SELECT * FROM meta_ad_insights_daily')).rows[0];
assert.equal(Number(row.purchases),6); assert.equal(Number(row.purchase_value),600);
assert.equal(Number(row.roas),5); assert.equal(Number(row.add_to_cart),12); assert.equal(Number(row.initiate_checkout),8);
console.log('PASS normalized funnel persisted without alias double counting');
assert.equal((await db.query('SELECT count(*) AS n FROM meta_review_creative_observations')).rows[0].n,2);
assert.equal((await db.query('SELECT count(*) AS n FROM meta_creatives')).rows[0].n,1);
assert.equal((await db.query('SELECT count(*) AS n FROM meta_ads')).rows[0].n,2);
console.log('PASS immutable creative observation deduplicated');
const before=JSON.stringify((await db.query('SELECT * FROM meta_ad_insights_daily')).rows);
await assert.rejects(sync(true));
assert.equal(JSON.stringify((await db.query('SELECT * FROM meta_ad_insights_daily')).rows),before);
console.log('PASS failed sync rollback preserves previous history');
await db.query("INSERT INTO ads_action_log(action_type,context) VALUES('meta_review_selection',$1::jsonb)",[JSON.stringify({overall:'1',account_id:'123',image:'chosen'})]);
await db.query('INSERT INTO meta_review_media(sha256,content_type,data) VALUES($1,$2,$3)',['digest','image/png',new Uint8Array([1,2,3])]);
const dumped=await db.dumpDataDir(); await db.close(); db=new PGlite({loadDataDir:dumped});
assert.equal((await db.query("SELECT context->>'image' AS chosen FROM ads_action_log WHERE action_type='meta_review_selection'")).rows[0].chosen,'chosen');
assert.equal((await db.query('SELECT octet_length(data) AS n FROM meta_review_media')).rows[0].n,3);
console.log('PASS selection and image persist after database restart');
const handoffCommands=JSON.parse(execFileSync('.venv/Scripts/python.exe',['-m','tests.meta_review_sql_fixture','--handoff'],{encoding:'utf8'}));
async function executeCommand(command,params=command.params){let n=0; return db.query(command.sql.replace(/%s/g,()=>'$'+(++n)),params);}
await executeCommand(handoffCommands.find(c=>c.sql.startsWith('INSERT')));
const handoffDump=await db.dumpDataDir(); await db.close(); db=new PGlite({loadDataDir:handoffDump});
const handoffLookup=handoffCommands.find(c=>c.sql.startsWith('SELECT context'));
const persisted=(await executeCommand(handoffLookup)).rows[0].context;
assert.equal(persisted.components.primary_text.value,'Exact primary\n\nNo rewriting');
assert.equal(persisted.components.headline.value,'Exact headline');
assert.equal(persisted.image_sha256,'digest');
assert.equal((await executeCommand(handoffLookup,['a'.repeat(32),'other-account'])).rows.length,0);
console.log('PASS actual durable handoff SQL survives restart and enforces account scope');
assert.deepEqual((await db.query('SELECT * FROM edition_guard')).rows,[{next_number:101,sold:100,remaining:0}]);
console.log('PASS unrelated edition state untouched');
const policies=(await db.query("SELECT relrowsecurity FROM pg_class WHERE relname IN ('meta_review_asset_daily','meta_review_media','meta_review_creative_observations')")).rows;
assert.equal(policies.length,3); assert.ok(policies.every(row=>row.relrowsecurity));
console.log('PASS all new tables protected by RLS');
const reads=JSON.parse(execFileSync('.venv/Scripts/python.exe',['-m','tests.meta_review_sql_fixture','--read'],{encoding:'utf8'}));
await db.exec('BEGIN');
for(const command of reads){let n=0; await db.query(command.sql.replace(/%s/g,()=>'$'+(++n)),command.params||[]);}
await db.exec('COMMIT');
console.log('PASS actual read-only history loader SQL');
await db.close();
