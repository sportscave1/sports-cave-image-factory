// Real PostgreSQL/PLpgSQL execution in isolated PGlite; no production connection.
// npm install --prefix <temporary-dir> @electric-sql/pglite@0.5.8
// PGLITE_MODULE=<temporary-dir>/node_modules/@electric-sql/pglite/dist/index.js node this-file
import {pathToFileURL} from 'node:url';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const {PGlite}=await import(pathToFileURL(process.env.PGLITE_MODULE).href);
const db=new PGlite();
const sql=readFileSync(new URL('../migrations/20260912045939_independent_edition_cursor.sql',import.meta.url),'utf8');
const strings='source_channel external_order_id external_line_item_id allocation_key shopify_product_gid shopify_order_id shopify_order_name shopify_line_item_id shopify_product_id shopify_variant_id shopify_handle product_title edition_name variant_title sku customer_name customer_email shopify_customer_name shopify_customer_email certificate_status status source mirror_status'.split(' ');
await db.exec(`
CREATE TABLE edition_products(id serial primary key, shopify_product_gid text unique, shopify_product_id text, shopify_handle text, product_title text, active_edition_run_id uuid, edition_total int, next_edition_number int, sold_count int, remaining_count int, last_assigned_edition int default 0, active boolean default true, sold_out boolean default false, is_sold_out boolean default false, updated_at timestamptz);
CREATE TABLE edition_runs(id uuid primary key, edition_total int, next_edition_number int, status text, edition_name text, allocation_baseline_sold_count int default 0, allocation_baseline_recorded_at timestamptz, allocation_baseline_reason text, updated_at timestamptz);
CREATE TABLE edition_orders(id serial primary key, ${strings.map(s=>s+' text').join(',')}, edition_run_id uuid, unit_ordinal int, edition_number int, edition_total int, allocation_index int, quantity int, identity_enforced boolean, allocation_valid boolean default true, assigned_at timestamptz, updated_at timestamptz, UNIQUE(source_channel,external_order_id,external_line_item_id,unit_ordinal), UNIQUE(edition_run_id,edition_number));
CREATE TABLE edition_allocation_tombstones(source_channel text, external_order_id text, external_line_item_id text, shopify_product_gid text, former_edition_number int);
`);
const originalLedger=readFileSync(new URL("../migrations/20260825_atomic_edition_allocation_ledger.sql",import.meta.url),"utf8");
await db.exec(originalLedger.slice(originalLedger.indexOf("CREATE OR REPLACE FUNCTION enforce_edition_order_ledger_writes()"),originalLedger.indexOf("-- Allocate every unit")));
await db.exec(sql);
const run='9799b113-0ff2-4dd6-9185-381357d04748', product='gid://shopify/Product/10431944393011';
async function reset(next=50,sold=0) {
 await db.exec('TRUNCATE edition_orders,edition_allocation_tombstones,edition_products,edition_runs');
 await db.query('INSERT INTO edition_runs(id,edition_total,next_edition_number,status) VALUES($1,100,$2,\'active\')',[run,next]);
 await db.query('INSERT INTO edition_products(shopify_product_gid,active_edition_run_id,edition_total,next_edition_number,sold_count,remaining_count) VALUES($1,$2,100,$3,$4,$5)',[product,run,next,sold,100-sold]);
}
async function allocate(qty=1,line='17545899573555',order='7408832905523',variant='54020683989299') {
 const r=await db.query('SELECT allocate_edition_line_units_atomic($1,$2,$3,$4,$5,$6,$7,$8,$9) result',['shopify',order,line,product,qty,order,'#SC3148',line,variant]);
 return r.rows.map(r=>r.result);
}
async function state(){return (await db.query('SELECT next_edition_number,sold_count,remaining_count FROM edition_products')).rows[0];}
let passed=0;
async function test(name,fn){await reset();await fn();passed++;console.log('PASS '+name);}
await test('previous production RPC reproduces exact pre-loop failure',async()=>{await db.exec(readFileSync(new URL('../migrations/20260828_fix_sparse_legacy_allocator.sql',import.meta.url),'utf8'));await assert.rejects(allocate(2),/Atomic edition suffix is not contiguous/);assert.deepEqual(await state(),{next_edition_number:50,sold_count:0,remaining_count:100});await db.exec(sql);});
await test('SC3148 cursor50 sold0 valid; two units50/51 and sales2',async()=>{const r=await allocate(2);assert.deepEqual(r.map(x=>x.allocation.edition_number),[50,51]);assert.deepEqual(await state(),{next_edition_number:52,sold_count:2,remaining_count:98});});
await test('single unit consumes50 and increments sales by one',async()=>{assert.equal((await allocate())[0].allocation.edition_number,50);assert.equal((await state()).sold_count,1);});
await test('two separate lines share product sequence',async()=>{await allocate();const r=await allocate(1,'222');assert.equal(r[0].allocation.edition_number,51);});
await test('different variants share sequence',async()=>{await allocate();assert.equal((await allocate(1,'222','7408832905523','999'))[0].allocation.edition_number,51);});
await test('duplicate delivery and numeric/GID aliases harmless',async()=>{await allocate(2);const before=await state();const r=await allocate(2,'gid://shopify/LineItem/17545899573555','gid://shopify/Order/7408832905523','gid://shopify/ProductVariant/54020683989299');assert(r.every(x=>!x.was_created));assert.deepEqual(await state(),before);});
await test('rollback midway commits no units/counters',async()=>{await db.exec('BEGIN');await allocate(2);await db.exec('ROLLBACK');assert.equal((await state()).next_edition_number,50);assert.equal((await allocate(2))[1].allocation.edition_number,51);});
await test('legacy partial commit keeps first and fills missing unit',async()=>{await allocate();await db.exec('UPDATE edition_orders SET quantity=2');const r=await allocate(2);assert.deepEqual(r.map(x=>x.was_created),[false,true]);assert.deepEqual(r.map(x=>x.allocation.edition_number),[50,51]);assert.equal((await state()).sold_count,2);});
await test('simultaneously submitted paid orders have unique numbers',async()=>{const rr=await Promise.all([allocate(2,'1','1'),allocate(2,'2','2')]);assert.deepEqual(rr.flat().map(x=>x.allocation.edition_number).sort(),[50,51,52,53]);});
await test('manual pointer override retains independent sales',async()=>{await allocate();await db.exec('UPDATE edition_products SET next_edition_number=70; UPDATE edition_runs SET next_edition_number=70');assert.equal((await allocate(1,'2'))[0].allocation.edition_number,70);assert.equal((await state()).sold_count,2);});
await test('new registered active run starts at1',async()=>{await reset(1);assert.equal((await allocate())[0].allocation.edition_number,1);});
await test('disabled run fails without writes',async()=>{await db.exec('UPDATE edition_products SET active=false');await assert.rejects(allocate(),/disabled/);assert.equal((await state()).sold_count,0);});
await test('sold-out run stays closed; successful retry is safe',async()=>{await reset(100,0);await allocate();await assert.rejects(allocate(1,'2'),/sold out/);assert.equal((await allocate())[0].was_created,false);});
await test('missing active run fails without creating state',async()=>{await db.exec('UPDATE edition_products SET active_edition_run_id=NULL');await assert.rejects(allocate(),/no active/);assert.equal((await state()).next_edition_number,50);});
await test('occupied number and backwards cursor rejected',async()=>{await allocate();await db.exec('UPDATE edition_products SET next_edition_number=50; UPDATE edition_runs SET next_edition_number=50');await assert.rejects(allocate(1,'2'),/issued or reserved/);});
await test('tombstoned/reserved number rejected',async()=>{await db.query('INSERT INTO edition_allocation_tombstones(shopify_product_gid,former_edition_number) VALUES($1,50)',[product]);await assert.rejects(allocate(),/issued or reserved/);});
await test('variant identity conflict rejected on retry',async()=>{await allocate();await assert.rejects(allocate(1,'17545899573555','7408832905523','other'),/conflicting identities/);});
assert(sql.includes('pg_advisory_xact_lock') && sql.includes('FOR UPDATE'));
console.log(`${passed} PostgreSQL scenarios passed. PGlite serializes connections; cross-process locking is provided by PostgreSQL transaction locks and database unique constraints.`);
await db.close();
