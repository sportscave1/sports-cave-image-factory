"""Synthetic only; fixed loopback PostgreSQL, private disposable schemas, no providers."""
import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

import shopify_financial_canary as canary

DSN = "postgresql://postgres@127.0.0.1:15469/ai_restore_20261106?sslmode=disable"
AT = datetime(2026, 11, 6, 3, tzinfo=timezone.utc)
SHA = "a" * 40  # Synthetic test revision, never a release candidate.
IDS = ["gid://shopify/Order/" + str(900000 + n) for n in range(6)]


class CanaryTests(unittest.TestCase):
    def setUp(self):
        self.schema = "source_canary_" + uuid4().hex
        self.conn = psycopg.connect(DSN, row_factory=dict_row, autocommit=True)
        self.conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
        self.conn.execute("""CREATE TABLE shopify_orders(
          shopify_order_id text PRIMARY KEY,total_price text,currency text,
          processed_at timestamptz,remote_updated_at timestamptz,synced_at timestamptz,updated_at timestamptz,
          cancelled_at timestamptz,fulfillment_status text,customer_email text,
          raw_json jsonb,raw jsonb);
          CREATE TABLE audit_logs(id bigserial PRIMARY KEY,event_type text,entity_type text,entity_id text,
            old_value jsonb,new_value jsonb,reason text,actor text,source text,created_at timestamptz DEFAULT now());
          CREATE TABLE edition_orders(id integer PRIMARY KEY,allocation text);
          CREATE TABLE edition_counters(id integer PRIMARY KEY,counter integer);
          CREATE TABLE certificates(id integer PRIMARY KEY,reference text);
          CREATE TABLE shopify_order_lines(id integer PRIMARY KEY,quantity integer);
          INSERT INTO edition_orders VALUES(1,'reserved');
          INSERT INTO edition_counters VALUES(1,45);
          INSERT INTO certificates VALUES(1,'synthetic');
          INSERT INTO shopify_order_lines VALUES(1,1)""")
        # Absent, explicit JSON null, blank, numeric zero, SQL NULL, and one known component.
        raw_values = [
            {"shipping_override": "retain"},
            {"total_price": None, "currency": None, "refund_workflow": "retain"},
            {"total_price": "", "currency": "", "fulfilment": "retain"},
            {"total_price": 0, "currency": "AUD", "notes": "synthetic"},
            None,
            {"currency": "AUD", "workflow": {"state": "retain"}},
        ]
        self.provider = {"captured_at": AT.isoformat(), "credential_context": "OS Shopify server integration",
                         "shop_domain": "synthetic.myshopify.com", "served_api_version": "2026-04", "rows": []}
        for n, identifier in enumerate(IDS):
            self.conn.execute("""INSERT INTO shopify_orders VALUES(
                %s,'','',%s,%s,%s,%s,NULL,'fulfilled','synthetic@example.invalid',%s::jsonb,%s::jsonb)""",
                (identifier, AT-timedelta(days=1), AT-timedelta(hours=1), AT, AT,
                 json.dumps(raw_values[n]) if raw_values[n] is not None else None,
                 json.dumps(raw_values[n]) if raw_values[n] is not None else None))
            self.provider["rows"].append({"id": identifier, "processedAt": (AT-timedelta(days=1)).isoformat(),
                "updatedAt": (AT-timedelta(hours=1)).isoformat(),
                "totalPriceSet": {"shopMoney": {"amount": "0.00" if n == 3 else "12.30", "currencyCode": "AUD"}}})
        self.ledger = {"captured_at": AT.isoformat(), "rows": canary.read_rows(self.conn, IDS)}
        self.contract = canary.read_contract(self.conn)
        self.manifest = canary.prepare(IDS, self.ledger, self.provider, self.contract)

    def tearDown(self):
        self.conn.rollback()
        self.conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
        self.conn.close()

    def approval(self, action="apply"):
        return {"release_sha": SHA, "operation_hash": self.manifest["operation_hash"], "action": action,
                "order_ids": IDS, "actor": "synthetic.operator", "approval_ref": "synthetic-test",
                "approved_at": (AT-timedelta(seconds=10)).isoformat(),
                "expires_at": (AT+timedelta(minutes=5)).isoformat()}

    def apply(self, **kwargs):
        return canary.apply(self.conn, self.manifest, kwargs.pop("approval", self.approval()),
                            kwargs.pop("provider", self.provider), runtime_revision=SHA, at=AT, **kwargs)

    def rollback(self):
        return canary.rollback(self.conn, self.manifest, self.approval("rollback"), runtime_revision=SHA, at=AT)

    def snapshot(self):
        return {table: self.conn.execute(sql.SQL("SELECT * FROM {} ORDER BY 1").format(sql.Identifier(table))).fetchall()
                for table in ("shopify_orders", "audit_logs", "edition_orders", "edition_counters", "certificates", "shopify_order_lines")}

    def test_apply_repeat_rollback_repeat_exact_fields_and_related_tables(self):
        before = self.snapshot()
        self.assertEqual(self.apply()["writes"], 6)
        applied = self.snapshot()
        for table in ("edition_orders", "edition_counters", "certificates", "shopify_order_lines"):
            self.assertEqual(applied[table], before[table])
        for prior, current in zip(before["shopify_orders"], applied["shopify_orders"]):
            self.assertEqual({k: v for k, v in prior.items() if k not in ("total_price", "currency", "raw_json", "raw", "updated_at")},
                             {k: v for k, v in current.items() if k not in ("total_price", "currency", "raw_json", "raw", "updated_at")})
        self.assertEqual(self.apply()["status"], "already_applied")
        self.assertEqual(self.snapshot(), applied)
        self.assertTrue(canary.reconcile(self.conn, self.manifest)["state_verified"])
        self.assertEqual(self.rollback()["writes"], 6)
        restored = self.snapshot()
        for prior, current in zip(before["shopify_orders"], restored["shopify_orders"]):
            self.assertEqual({k: v for k, v in prior.items() if k != "updated_at"},
                             {k: v for k, v in current.items() if k != "updated_at"})
        self.assertEqual(self.rollback()["status"], "already_rolled_back")
        self.assertEqual(self.snapshot(), restored)
        self.assertEqual(len(restored["audit_logs"]), 2)
        with self.assertRaises(canary.Conflict): self.apply()
        self.assertTrue(canary.reconcile(self.conn, self.manifest)["state_verified"])

    def test_changed_before_images_abort_all_rows(self):
        for field, value in (("total_price", "25"), ("fulfillment_status", "cancelled"), ("updated_at", AT+timedelta(seconds=1))):
            with self.subTest(field=field):
                saved = self.conn.execute(sql.SQL("SELECT {} FROM shopify_orders WHERE shopify_order_id=%s").format(sql.Identifier(field)), (IDS[-1],)).fetchone()[field]
                self.conn.execute(sql.SQL("UPDATE shopify_orders SET {}=%s WHERE shopify_order_id=%s").format(sql.Identifier(field)), (value, IDS[-1]))
                before = self.snapshot()
                with self.assertRaises(canary.Conflict): self.apply()
                self.assertEqual(self.snapshot(), before)
                self.conn.execute(sql.SQL("UPDATE shopify_orders SET {}=%s WHERE shopify_order_id=%s").format(sql.Identifier(field)), (saved, IDS[-1]))

    def test_partial_failure_is_atomic_and_next_attempt_recovers(self):
        original = canary.write_financial
        count = 0
        def fail_second(*args):
            nonlocal count
            count += 1
            if count == 2: raise RuntimeError("synthetic interrupted step")
            return original(*args)
        before = self.snapshot()
        with patch.object(canary, "write_financial", side_effect=fail_second):
            with self.assertRaises(RuntimeError): self.apply()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.apply()["writes"], 6)

    def test_audit_insert_failure_rolls_back_financial_writes(self):
        self.conn.execute("ALTER TABLE audit_logs ADD CHECK(event_type='never')")
        before = self.snapshot()
        with self.assertRaises(psycopg.errors.CheckViolation): self.apply()
        self.assertEqual(before, self.snapshot())
        self.conn.execute("ALTER TABLE audit_logs DROP CONSTRAINT audit_logs_event_type_check")
        self.assertEqual(self.apply()["writes"], 6)

    def test_post_write_guard_mutation_rolls_back(self):
        original = canary.write_financial
        def simulate_guard(conn, identifier, values):
            original(conn, identifier, values)
            conn.execute("UPDATE shopify_orders SET fulfillment_status='CANCELLED' WHERE shopify_order_id=%s", (identifier,))
        before = self.snapshot()
        with patch.object(canary, "write_financial", side_effect=simulate_guard):
            with self.assertRaisesRegex(canary.Conflict, "Post-write"): self.apply()
        self.assertEqual(before, self.snapshot())

    def test_contract_drift_and_unreviewed_trigger_block(self):
        self.conn.execute("""CREATE FUNCTION test_guard() RETURNS trigger LANGUAGE plpgsql AS
          $$BEGIN RETURN NEW; END$$;
          CREATE TRIGGER test_guard BEFORE UPDATE ON shopify_orders FOR EACH ROW EXECUTE FUNCTION test_guard()""")
        before = self.snapshot()
        with self.assertRaisesRegex(canary.Conflict, "contract changed"): self.apply()
        with self.assertRaisesRegex(canary.Conflict, "Unreviewed"):
            canary.prepare(IDS, self.ledger, self.provider, canary.read_contract(self.conn))
        self.assertEqual(before, self.snapshot())

    def test_rollback_never_overwrites_later_business_work(self):
        self.apply()
        self.conn.execute("UPDATE shopify_orders SET fulfillment_status='changed' WHERE shopify_order_id=%s", (IDS[-1],))
        before = self.snapshot()
        with self.assertRaisesRegex(canary.Conflict, "After-image"): self.rollback()
        with self.assertRaisesRegex(canary.Conflict, "final state"): self.apply()
        self.assertFalse(canary.reconcile(self.conn, self.manifest)["state_verified"])
        self.assertEqual(before, self.snapshot())

    def test_uncertain_committed_response_reconciles_without_duplicate(self):
        real = self.conn
        class LostAck:
            info = real.info
            execute = real.execute
            @contextmanager
            def transaction(self):
                with real.transaction(): yield
                raise psycopg.OperationalError("synthetic lost commit acknowledgement")
        with self.assertRaises(canary.OutcomeUnknown):
            canary.apply(LostAck(), self.manifest, self.approval(), self.provider, runtime_revision=SHA, at=AT)
        self.assertTrue(canary.reconcile(self.conn, self.manifest)["state_verified"])
        self.assertEqual(self.apply()["writes"], 0)
        self.assertEqual(len(self.snapshot()["audit_logs"]), 1)

    def test_two_concurrent_callers_have_one_durable_apply(self):
        barrier = threading.Barrier(2)
        def caller():
            with psycopg.connect(DSN, row_factory=dict_row, autocommit=True) as conn:
                conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self.schema)))
                barrier.wait(timeout=3)
                return canary.apply(conn, self.manifest, self.approval(), self.provider, runtime_revision=SHA, at=AT)["writes"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(caller) for _ in range(2)]
            self.assertEqual(sorted(f.result(timeout=10) for f in futures), [0, 6])
        self.assertEqual(len(self.snapshot()["audit_logs"]), 1)

    def test_exact_approval_and_tampered_manifest_fail_closed(self):
        before = self.snapshot()
        variants = {"operation_hash": "wrong", "release_sha": "b"*40, "action": "rollback", "order_ids": IDS[:-1],
                    "actor": "", "approval_ref": "contains space", "approved_at": (AT+timedelta(seconds=1)).isoformat(),
                    "expires_at": AT.isoformat(), "unnecessary_sensitive_field": "not permitted"}
        for field, value in variants.items():
            with self.subTest(field=field):
                approval = {**self.approval(), field: value}
                with self.assertRaises(PermissionError): self.apply(approval=approval)
        corrupted = copy.deepcopy(self.manifest)
        corrupted["changes"][0]["after"]["total_price"] = "500"
        with self.assertRaises(canary.Conflict):
            canary.apply(self.conn, corrupted, self.approval(), self.provider, runtime_revision=SHA, at=AT)
        self.assertEqual(before, self.snapshot())

    def test_provider_staleness_changes_and_missing_coverage_block(self):
        before = self.snapshot()
        cases = []
        for captured in (AT-timedelta(seconds=301), AT+timedelta(seconds=1)):
            p = copy.deepcopy(self.provider); p["captured_at"] = captured.isoformat(); cases.append(p)
        for key, value in (("credential_context", "connector"), ("shop_domain", "other.myshopify.com"), ("served_api_version", "2026-07")):
            p = copy.deepcopy(self.provider); p[key] = value; cases.append(p)
        p = copy.deepcopy(self.provider); p["rows"].pop(); cases.append(p)
        p = copy.deepcopy(self.provider); p["rows"][0]["updatedAt"] = AT.isoformat(); cases.append(p)
        p = copy.deepcopy(self.provider); p["rows"][0]["totalPriceSet"]["shopMoney"]["amount"] = "15"; cases.append(p)
        p = copy.deepcopy(self.provider); p["rows"][0]["totalPriceSet"]["shopMoney"]["currencyCode"] = "USD"; cases.append(p)
        for n, p in enumerate(cases):
            with self.subTest(case=n):
                with self.assertRaises(canary.Conflict): self.apply(provider=p)
        self.assertEqual(before, self.snapshot())
        with self.assertRaises(canary.Conflict):
            canary.apply(self.conn, self.manifest, {**self.approval(), "expires_at": (AT+timedelta(hours=1)).isoformat()},
                         {**self.provider, "captured_at": (AT+timedelta(minutes=6)).isoformat()},
                         runtime_revision=SHA, at=AT+timedelta(minutes=6))

    def test_cancelled_conflicting_and_oversize_prepare_rejected(self):
        for changed in ({"cancelled_at": AT.isoformat()}, {"raw_type": "array"},
                        {"raw_amount": "30"}, {"raw_currency": "USD"}):
            ledger = copy.deepcopy(self.ledger); ledger["rows"][0].update(changed)
            with self.assertRaises(canary.Conflict): canary.prepare(IDS, ledger, self.provider, self.contract)
        with self.assertRaises(ValueError):
            canary.prepare(IDS+["gid://shopify/Order/9999999"], self.ledger, self.provider, self.contract)
        self.assertEqual(canary.reconcile(self.conn, self.manifest)["status"], "not_applied")

    def test_timestamp_normalization_and_preparation_repeatability(self):
        ledger = copy.deepcopy(self.ledger)
        ledger["rows"][0]["updated_at"] = "2026-11-06T03:00:00.000000+00:00"
        manifest = canary.prepare(IDS, ledger, self.provider, self.contract)
        self.assertEqual(manifest, self.manifest)
        self.assertEqual(self.apply()["writes"], 6)

    def test_unexpected_audit_history_blocks_replay(self):
        self.conn.execute("""INSERT INTO audit_logs(event_type,entity_type,entity_id,source)
            VALUES('unknown','financial_canary',%s,%s)""", (self.manifest["operation_hash"], canary.SOURCE))
        before = self.snapshot()
        with self.assertRaises(canary.Conflict): self.apply()
        with self.assertRaises(canary.Conflict): canary.reconcile(self.conn, self.manifest)
        self.assertEqual(before, self.snapshot())

    def test_actual_trigger_change_is_verified_and_atomically_rejected(self):
        self.conn.execute("""CREATE FUNCTION cancelled_guard() RETURNS trigger LANGUAGE plpgsql AS
          $$BEGIN NEW.total_price:='0.00'; NEW.fulfillment_status:='CANCELLED'; RETURN NEW; END$$;
          CREATE TRIGGER cancelled_edition_order_guard BEFORE UPDATE ON shopify_orders
          FOR EACH ROW EXECUTE FUNCTION cancelled_guard()""")
        contract = canary.read_contract(self.conn)
        # Synthetic equivalent only; never expand the production reviewed-function allowlist.
        with patch.object(canary, "REVIEWED_GUARD_MD5", contract["triggers"][0]["function_md5"]):
            self.manifest = canary.prepare(IDS, self.ledger, self.provider, contract)
        before = self.snapshot()
        with self.assertRaisesRegex(canary.Conflict, "Post-write"): self.apply()
        self.assertEqual(before, self.snapshot())

    def test_partial_rollback_failure_preserves_applied_state_then_recovers(self):
        self.apply()
        original = canary.write_financial
        count = 0
        def fail_second(*args):
            nonlocal count
            count += 1
            if count == 2: raise RuntimeError("synthetic rollback interruption")
            return original(*args)
        before = self.snapshot()
        with patch.object(canary, "write_financial", side_effect=fail_second):
            with self.assertRaises(RuntimeError): self.rollback()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.rollback()["writes"], 6)

    def test_missing_order_and_non_idle_connection_fail_without_writes(self):
        self.conn.execute("DELETE FROM shopify_orders WHERE shopify_order_id=%s", (IDS[-1],))
        before = self.snapshot()
        with self.assertRaisesRegex(canary.Conflict, "Missing canary"): self.apply()
        self.assertEqual(before, self.snapshot())
        with self.conn.transaction():
            with self.assertRaisesRegex(ValueError, "idle"): self.apply()


if __name__ == "__main__":
    unittest.main()
