"""Offline Phase 2 SQL parity/plans and read-latency benchmark.

Uses a new in-memory PGlite PostgreSQL engine on loopback, synthetic rows only.
No application server, production configuration, provider calls or migrations.
Test dependencies: @electric-sql/pglite 0.6.0, pglite-socket 0.3.0.
"""
import argparse
import ast
from contextlib import contextmanager, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@contextmanager
def local_database(modules):
    from scripts.benchmark_app_startup import child_environment
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="phase2-sql-") as directory:
        logfile = Path(directory) / "database.log"
        with logfile.open("w+", encoding="utf-8") as log:
            process = subprocess.Popen(["node", str(ROOT/"tests/fixtures/data_performance_server.mjs"),
                str(modules.resolve()), str(port)], cwd=directory, env=child_environment(),
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                deadline = time.monotonic()+25
                while "READY" not in logfile.read_text(encoding="utf-8"):
                    if process.poll() is not None or time.monotonic()>deadline:
                        raise RuntimeError("Disposable SQL engine failed: "+logfile.read_text(encoding="utf-8"))
                    time.sleep(.05)
                yield f"postgresql://postgres@127.0.0.1:{port}/postgres?sslmode=disable"
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


def functions(source, db):
    names = {"load_home_weekly_work_bundle", "list_hybrid_order_rows"}
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
    namespace = dict(vars(db))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<phase2 measured readers>", "exec"), namespace)
    return namespace


def allocation_sql(reader, db):
    from tests.test_orders_bounded_reader import ProductionCardinalityDatabase
    from tests.read_connection_fakes import disposable_read_connection
    fixture = ProductionCardinalityDatabase(order_count=560, lines_per_order=2)
    with patch.object(db, "connect", fixture.connect), patch.object(db, "read_connection", disposable_read_connection), redirect_stdout(io.StringIO()):
        reader(limit=50)
    return next((sql, params) for sql, params in fixture.statements if "WITH selected_edition_ids" in sql)


def seed(conn, certificates=25000):
    conn.execute("""
        CREATE TABLE os_users(id text PRIMARY KEY, username text, email text,
          display_name text, role text, timezone text, is_active bool, account_status text);
        CREATE TABLE daily_execution_sheets(id uuid PRIMARY KEY, user_id text, user_name text,
          sheet_date date, status text, top_tasks jsonb, additional_items jsonb, planning_data jsonb);
        CREATE TABLE daily_execution_task_timers(id uuid PRIMARY KEY, sheet_id uuid, user_id text,
          task_type text, task_index int, status text, allocated_seconds int, actual_elapsed_seconds int);
        CREATE TABLE human_work_events(id uuid PRIMARY KEY, user_id text, origin text,
          occurred_at timestamptz, action_type text, description text, area text, outcome text,
          entity_type text, entity_id text, source_route text, correlation_key text,
          actual_seconds int, metadata jsonb);
        CREATE INDEX home_sheet_user_date ON daily_execution_sheets(user_id,sheet_date);
        CREATE INDEX home_work_user_date ON human_work_events(user_id,occurred_at);
        INSERT INTO os_users VALUES
          ('alice','alice','alice@example.invalid','Alice','admin','Australia/Sydney',true,'active'),
          ('bob','bob','bob@example.invalid','Bob','worker','Australia/Sydney',true,'active'),
          ('removed','removed','','Removed','worker','Australia/Sydney',false,'removed');
        INSERT INTO daily_execution_sheets
        SELECT md5('sheet'||i)::uuid, u, u, '2026-11-23'::date, 'active',
          '[{"task":"Synthetic task","completed":true,"status":"Done","time_blocked":"30"}]'::jsonb,
          '[]'::jsonb, '{}'::jsonb FROM generate_series(1,3) i,
          LATERAL (SELECT CASE i WHEN 1 THEN 'alice' WHEN 2 THEN 'bob' ELSE 'removed' END u) users;
        INSERT INTO daily_execution_task_timers
        SELECT md5('timer'||user_id)::uuid,id,user_id,'top',0,'completed',1800,600 FROM daily_execution_sheets;
        INSERT INTO human_work_events
        SELECT md5('work'||i)::uuid, CASE WHEN i%2=0 THEN 'alice' ELSE 'bob' END, 'human',
          '2026-11-24T00:00:00Z'::timestamptz, 'product_created','Synthetic product work','Products','completed',
          'product', i::text,'Products','synthetic-work-'||i,20,'{}'::jsonb FROM generate_series(1,30) i;
        CREATE TABLE edition_orders(id uuid PRIMARY KEY, shopify_order_id text, shopify_order_name text,
          shopify_line_item_id text, shopify_product_id text, shopify_variant_id text, shopify_handle text,
          product_handle text, product_title text, variant_title text, sku text, customer_name text,
          customer_email text, edition_number int, edition_total int, allocation_index int,
          assigned_at timestamptz, certificate_status text, status text, source text,
          manual_override bool, allocation_valid bool);
        CREATE INDEX edition_line ON edition_orders(shopify_line_item_id);
        CREATE INDEX edition_order ON edition_orders(shopify_order_id);
        CREATE TABLE certificates(id bigint PRIMARY KEY, edition_order_id text UNIQUE,
          related_edition_order_id uuid, certificate_id text, local_file_path text, shopify_file_url text,
          certificate_file_url text, certificate_pdf_url text, certificate_print_jpg_url text,
          certificate_preview_image_url text, shopify_pdf_file_id text, shopify_print_jpg_file_id text,
          shopify_preview_file_id text, asset_sync_status text, asset_sync_error text,
          generated_at timestamptz, updated_at timestamptz, certificate_r2_bucket text,
          certificate_r2_key text, certificate_preview_r2_bucket text, certificate_preview_r2_key text);
        CREATE INDEX idx_certificates_related_edition_order ON certificates(related_edition_order_id);
        INSERT INTO edition_orders(id,shopify_order_id,shopify_line_item_id,edition_number,
          edition_total,allocation_index,allocation_valid)
        SELECT md5('edition'||(n*10+j))::uuid,'gid://shopify/Order/'||n,
          'gid://shopify/LineItem/'||(n*10+j),1,100,1,true
          FROM generate_series(1,1000) n, generate_series(0,1) j;
    """)
    conn.execute("""
        INSERT INTO certificates(id,edition_order_id,related_edition_order_id,certificate_id,
          shopify_file_url,updated_at)
        SELECT i,md5('edition'||i)::uuid::text,
          CASE WHEN i%%2=0 THEN md5('edition'||i)::uuid END,
          'synthetic-certificate-'||i,'https://assets.invalid/certificate.pdf','2026-11-24'::timestamptz
        FROM generate_series(1,%s) i
    """, (certificates,))
    conn.execute("ANALYZE")


def compare(before, after, samples):
    # Alternate order so a candidate does not always benefit from going second.
    values, answers = {"before":[],"after":[]}, {}
    for index in range(samples):
        for label,fn in ([("before",before),("after",after)] if index%2==0 else
                         [("after",after),("before",before)]):
            began = time.perf_counter()
            answers[label] = fn()
            values[label].append((time.perf_counter()-began)*1000)
    stats = {key:dict(n=samples,median_ms=round(statistics.median(times),3),
        first_ms=round(times[0],3),min_ms=round(min(times),3),max_ms=round(max(times),3),
        samples_ms=[round(value,3) for value in times]) for key,times in values.items()}
    return answers["before"],stats["before"],answers["after"],stats["after"]


def plan_nodes(plan):
    yield plan
    for child in plan.get("Plans", []):
        yield from plan_nodes(child)


def run(args):
    from scripts.startup_fixture_server import deny_external_network
    sys.addaudithook(deny_external_network)
    import psycopg
    from psycopg.rows import dict_row
    import database_read_pool as pools
    import supabase_backend as db
    import sports_cave_dashboard as dashboard
    from datetime import datetime
    from zoneinfo import ZoneInfo

    before_source = args.before.read_text(encoding="utf-8") if args.before else subprocess.check_output(
        ["git","show","333d9a9d481bb96c0c84fb42bbfa80a8a7f26d35:supabase_backend.py"], cwd=ROOT, text=True, encoding="utf-8")
    # Capture actual production allocation SQL using the existing SQL-aware fake.
    old = functions(before_source, db)
    old_sql, old_params = allocation_sql(old["list_hybrid_order_rows"], db)
    new_sql, new_params = allocation_sql(db.list_hybrid_order_rows, db)
    evidence = dict(scope="Synthetic local PostgreSQL/WASM SQL parity and plans; not production latency",
        source_sha256=hashlib.sha256((ROOT/"supabase_backend.py").read_bytes()).hexdigest(),
        baseline_sha256=hashlib.sha256(before_source.encode()).hexdigest(), certificates=args.certificates,
        baseline_source="explicit local pre-Phase-2 snapshot" if args.before else "333d9a9d:supabase_backend.py",
        harness_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
            "scripts/benchmark_app_data.py","scripts/local_pg_latency.py","tests/fixtures/data_performance_server.mjs")},
        test_dependencies={name:json.loads((args.modules/name/"package.json").read_text(encoding="utf-8"))["version"]
                           for name in ("@electric-sql/pglite","@electric-sql/pglite-socket")},
        allocation_output_equal=False, home_output_equal=False)
    try:
        with local_database(args.modules) as dsn:
            def fresh():
                return psycopg.connect(dsn, autocommit=False, row_factory=dict_row, prepare_threshold=None)
            @contextmanager
            def pooled():
                with pools.connection(dsn) as conn:
                    yield conn
            with psycopg.connect(dsn,autocommit=True,row_factory=dict_row) as setup:
                evidence["engine"] = setup.execute("SELECT version() AS version").fetchone()["version"]
                seed(setup,args.certificates)
            with patch.object(db,"connect",fresh), patch.object(db,"read_connection",pooled), \
                    patch.object(db,"ensure_dashboard_schema"), redirect_stdout(io.StringIO()):
                old = functions(before_source,db)
                inputs = ("alice","2026-11-23","2026-11-29","2026-11-22T13:00:00Z","2026-11-24T03:00:00Z")
                before,evidence["home_before"],after,evidence["home_after"] = compare(
                    lambda: old["load_home_weekly_work_bundle"](*inputs,include_team=True),
                    lambda: db.load_home_weekly_work_bundle(*inputs,include_team=True),args.samples)
                evidence["home_output_equal"] = before==after
                with patch.object(dashboard,"get_supabase_backend",return_value=db):
                    user=dict(id="alice",role="admin",display_name="Alice")
                    now=datetime(2026,11,24,14,tzinfo=ZoneInfo("Australia/Sydney"))
                    with patch.object(db,"load_home_weekly_work_bundle",old["load_home_weekly_work_bundle"]):
                        old_summary=dashboard.build_home_weekly_work_snapshot(user,now)
                    evidence["home_metrics_equal"] = old_summary==dashboard.build_home_weekly_work_snapshot(user,now)
                # Use the same pooled lease and actual extracted allocation SQL.
                with pooled() as conn:
                    def query(sql,params):
                        return conn.execute(sql,params).fetchall()
                    old_rows,evidence["orders_before"],new_rows,evidence["orders_after"]=compare(
                        lambda:query(old_sql,old_params),lambda:query(new_sql,new_params),args.samples)
                    evidence["allocation_output_equal"]=old_rows==new_rows
                    evidence["allocation_rows"]=len(new_rows)
                    for label,sql,params in [("before",old_sql,old_params),("after",new_sql,new_params)]:
                        plan=conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "+sql,params).fetchone()["QUERY PLAN"][0]
                        evidence["orders_plan_"+label]=plan
                evidence["pools"]=pools.stats()
                # Separate modeled transport latency from the real loopback
                # SQL/plan measurements above. Never call this production speed.
                from scripts.local_pg_latency import delayed_database
                with delayed_database(dsn,20) as (slow_dsn,wire):
                    def slow_fresh():
                        return psycopg.connect(slow_dsn,autocommit=False,row_factory=dict_row,prepare_threshold=None)
                    @contextmanager
                    def slow_pooled():
                        with pools.connection(slow_dsn) as conn:
                            yield conn
                    try:
                        with patch.object(db,"connect",slow_fresh),patch.object(db,"read_connection",slow_pooled):
                            old_slow=functions(before_source,db)
                            left,evidence["home_delayed_before"],right,evidence["home_delayed_after"]=compare(
                                lambda:old_slow["load_home_weekly_work_bundle"](*inputs,include_team=True),
                                lambda:db.load_home_weekly_work_bundle(*inputs,include_team=True),args.samples)
                            evidence["home_delayed_equal"]=left==right
                            evidence["latency_model"]=dict(delay_ms=20,scope="One-way scheduled frontend transport delay; not WAN/TLS/production latency",
                                physical_connections=len(wire),protocol=wire)
                    finally:
                        pools.close()
        for key in ("home_output_equal","home_metrics_equal","allocation_output_equal","home_delayed_equal"):
            if evidence.get(key) is not True:
                raise AssertionError(key+" failed")
        nodes=list(plan_nodes(evidence["orders_plan_after"]["Plan"]))
        if not any("idx_certificates_related_edition_order"==n.get("Index Name") for n in nodes):
            raise AssertionError("Candidate did not use the existing certificate UUID index.")
        if hashlib.sha256((ROOT/"supabase_backend.py").read_bytes()).hexdigest()!=evidence["source_sha256"]:
            raise RuntimeError("Source changed during the benchmark; rerun.")
        for name,original in evidence["harness_sha256"].items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=original:
                raise RuntimeError("Benchmark source changed during the run; rerun.")
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(evidence,indent=2,default=str)+"\n",encoding="utf-8")
        print(json.dumps({k:v for k,v in evidence.items() if not k.startswith("orders_plan")},indent=2,default=str))
    finally:
        pools.close()


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules",type=Path,required=True)
    parser.add_argument("--before",type=Path)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--samples",type=int,default=5)
    parser.add_argument("--certificates",type=int,default=25000)
    args=parser.parse_args()
    if args.samples<1 or args.certificates<6000:
        parser.error("Use at least one sample and 6000 synthetic certificates.")
    run(args)
