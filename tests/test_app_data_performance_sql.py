"""Actual local PostgreSQL/WASM query parity. No production DSN is accepted."""
from contextlib import contextmanager, redirect_stdout
import io
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
import pytest

import supabase_backend as db
from scripts.benchmark_app_data import ROOT, allocation_sql, functions, local_database, seed


@pytest.fixture(scope="module")
def sql_fixture():
    configured=os.environ.get("LOCAL_APP_DATA_SQL_MODULES")
    modules = Path(configured) if configured else ROOT / ".tmp-startup-phase2/sql-engine/node_modules"
    if not (modules/"@electric-sql/pglite/dist/index.js").is_file():
        if configured:
            pytest.fail("LOCAL_APP_DATA_SQL_MODULES must point to the installed pinned fixture dependencies.")
        pytest.skip("Optional local SQL fixture: install the pinned dependencies from the Phase 2 report.")
    import subprocess
    source = subprocess.check_output(["git","show","HEAD:supabase_backend.py"],cwd=ROOT,
                                     text=True,encoding="utf-8")
    old = functions(source,db)
    before = allocation_sql(old["list_hybrid_order_rows"],db)
    after = allocation_sql(db.list_hybrid_order_rows,db)
    with local_database(modules) as dsn:
        # One physical session in this SQL fixture avoids PGlite multiplexer's
        # concurrency limits. Exclusive multi-reader pool behaviour is tested
        # separately in test_database_read_pool, not claimed from this engine.
        with ConnectionPool(dsn,min_size=1,max_size=1,kwargs=dict(
                autocommit=True,row_factory=dict_row,prepare_threshold=None)) as pool:
            with pool.connection() as conn:
                seed(conn,6000)
                conn.execute("SET statement_timeout=8000")
            yield SimpleNamespace(dsn=dsn,pool=pool,source=source,before=before,after=after)


@pytest.fixture
def home_readers(sql_fixture):
    @contextmanager
    def fresh():
        with psycopg.connect(sql_fixture.dsn,row_factory=dict_row,prepare_threshold=None) as conn:
            yield conn
    with patch.object(db,"connect",fresh), patch.object(db,"read_connection",sql_fixture.pool.connection), \
            patch.object(db,"ensure_dashboard_schema"), redirect_stdout(io.StringIO()):
        old = functions(sql_fixture.source,db)
        yield old["load_home_weekly_work_bundle"],db.load_home_weekly_work_bundle


INPUTS=("alice","2026-11-23","2026-11-29","2026-11-22T13:00:00Z","2026-11-24T03:00:00Z")


@pytest.mark.parametrize("team", [False,True])
def test_home_bundle_matches_and_respects_current_worker_team_and_removed_scope(home_readers,team):
    before,after=home_readers
    previous=before(*INPUTS,include_team=team)
    current=after(*INPUTS,include_team=team)
    assert current==previous
    assert {u["id"] for u in current["users"]}==({"alice","bob"} if team else {"alice"})
    assert all(event["user_id"]!="removed" for event in current["human_work"])
    assert all(sheet["user_id"]!="removed" for sheet in current["sheets"])


def test_home_reuses_lease_and_returns_timeout_and_transaction_to_original_state(sql_fixture,home_readers):
    _,after=home_readers
    with sql_fixture.pool.connection() as conn:
        original=conn.execute("SHOW statement_timeout").fetchone()["statement_timeout"]
    with patch.object(db,"connect",side_effect=AssertionError("Home opened a fresh connection")):
        assert after(*INPUTS)["users"]
        assert after(*INPUTS)["users"]
    with sql_fixture.pool.connection() as conn:
        assert conn.info.transaction_status==psycopg.pq.TransactionStatus.IDLE
        assert conn.execute("SHOW statement_timeout").fetchone()["statement_timeout"]==original
    assert sql_fixture.pool.get_stats()["connections_num"]==1


def test_home_does_not_cache_disabled_account_or_empty_results(sql_fixture,home_readers):
    before,after=home_readers
    assert after(*INPUTS)["users"]
    with sql_fixture.pool.connection() as conn:
        conn.execute("UPDATE os_users SET is_active=false WHERE id='alice'")
    try:
        empty=after(*INPUTS)
        assert empty==before(*INPUTS)
        assert all(empty[key]==[] for key in ("users","sheets","timers","human_work","activities"))
        assert empty["query_count"]==1
    finally:
        with sql_fixture.pool.connection() as conn:
            conn.execute("UPDATE os_users SET is_active=true WHERE id='alice'")
    assert after(*INPUTS)["users"]


def test_home_statement_timeout_is_applied_inside_read_and_not_retained(sql_fixture,home_readers):
    _,after=home_readers
    seen=[]
    execute=psycopg.Cursor.execute
    def track(cur,sql,*args,**kwargs):
        if "WITH permitted_users" in str(sql):
            # A separate cursor syncs the pipeline and observes the transaction
            # setting, without changing the actual SELECT.
            seen.append(cur.connection.execute("SHOW statement_timeout").fetchone()["statement_timeout"])
        return execute(cur,sql,*args,**kwargs)
    with patch.object(db,"_dashboard_query_timeout_ms",return_value=731), \
            patch.object(psycopg.Cursor,"execute",track):
        assert after(*INPUTS)["users"]
    assert seen==["731ms"]
    with sql_fixture.pool.connection() as conn:
        assert conn.execute("SHOW statement_timeout").fetchone()["statement_timeout"]=="8s"


def test_home_failed_select_rolls_back_and_same_lease_can_read_again(sql_fixture,home_readers):
    _,after=home_readers
    with sql_fixture.pool.connection() as conn:
        conn.execute("ALTER TABLE human_work_events RENAME TO fixture_hidden_work")
    try:
        with pytest.raises(db.DatabaseReadError):
            after(*INPUTS)
        with sql_fixture.pool.connection() as conn:
            assert conn.info.transaction_status==psycopg.pq.TransactionStatus.IDLE
            assert conn.execute("SHOW statement_timeout").fetchone()["statement_timeout"]=="8s"
    finally:
        with sql_fixture.pool.connection() as conn:
            conn.execute("ALTER TABLE fixture_hidden_work RENAME TO human_work_events")
    assert len(after(*INPUTS)["human_work"])==15


def test_home_stale_transport_retries_whole_read_once_without_caching_accounts(sql_fixture,home_readers):
    _,after=home_readers
    calls=[]
    closed=MagicMock(closed=False)
    closed.cursor.side_effect=psycopg.OperationalError("connection is closed")
    @contextmanager
    def lease():
        calls.append(True)
        if len(calls)==1:
            yield closed
        else:
            with sql_fixture.pool.connection() as conn:
                yield conn
    with patch.object(db,"read_connection",lease):
        assert after(*INPUTS)["users"]
    assert len(calls)==2
    assert db.get_last_database_read_diagnostic()["recovered"] is True
    closed.close.assert_called()


def test_allocation_query_output_matches_actual_sql(sql_fixture):
    with sql_fixture.pool.connection() as conn:
        assert conn.execute(*sql_fixture.before).fetchall()==conn.execute(*sql_fixture.after).fetchall()


def certificate_lookup(sql,identity):
    # Preserve the actual production LATERAL predicate, ranking and LIMIT.
    tail=sql.split("FROM certificates certificate",1)[1].split(") c ON TRUE",1)[0]
    return ("SELECT c.certificate_id FROM (VALUES (%s::text)) eo(id) LEFT JOIN LATERAL "
            "(SELECT certificate.* FROM certificates certificate "+tail+") c ON TRUE",(identity,))


@pytest.mark.parametrize("identity",[
    "1001", "not-a-uuid", "aabbccdd-1111-2222-3333-444455556666",
    "AABBCCDD-1111-2222-3333-444455556666",
])
def test_legacy_text_numeric_and_uppercase_identity_parity(sql_fixture,identity):
    with sql_fixture.pool.connection() as conn,conn.transaction(force_rollback=True):
        conn.execute("""INSERT INTO certificates(id,edition_order_id,related_edition_order_id,certificate_id)
            VALUES (1000000,%s,NULL,'legacy-synthetic')""",(identity,))
        old=conn.execute(*certificate_lookup(sql_fixture.before[0],identity)).fetchall()
        new=conn.execute(*certificate_lookup(sql_fixture.after[0],identity)).fetchall()
        assert old==new==[dict(certificate_id="legacy-synthetic")]


def test_preferred_link_conflicts_and_asset_priority_preserved(sql_fixture):
    target="aabbccdd-1111-2222-3333-444455556666"
    other="aabbccdd-1111-2222-3333-444455557777"
    with sql_fixture.pool.connection() as conn,conn.transaction(force_rollback=True):
        # A conflicting preferred link must not fall back to its legacy link.
        conn.execute("""INSERT INTO certificates(id,edition_order_id,related_edition_order_id,
          certificate_id,shopify_file_url,updated_at) VALUES
          (1000000,%s,%s::uuid,'conflict','https://assets.invalid/wrong','2026-11-24'),
          (1000001,'ready-old',%s::uuid,'ready','https://assets.invalid/right','2026-11-20'),
          (1000002,'new-without-asset',%s::uuid,'not-ready',NULL,'2026-11-25')
          """,(target,other,target,target))
        old=conn.execute(*certificate_lookup(sql_fixture.before[0],target)).fetchall()
        new=conn.execute(*certificate_lookup(sql_fixture.after[0],target)).fetchall()
        assert old==new==[dict(certificate_id="ready")]
        # Text uppercase IDs retain the former exact-string matching semantics.
        assert conn.execute(*certificate_lookup(sql_fixture.after[0],target.upper())).fetchall()==[
            dict(certificate_id=None)]
