import copy
from decimal import Decimal
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import psycopg
from psycopg.rows import dict_row
import shopify_sync
import supabase_backend as backend
import shopify_financial_repair as repair
from shopify_order_financials import graphql_financial_fields, money_pair
import meta_review_sync as sync
import meta_review_store as store
import meta_ads_client as meta

CONFIG = {"configured": True, "ad_account_id": "act_123", "api_version": "v26.0"}
ACCOUNT = {"account_id": "123", "name": "Synthetic", "currency": "AUD", "timezone_name": "Australia/Sydney"}
GID = "gid://shopify/Order/999999"
AT = datetime(2026, 11, 6, 0, tzinfo=timezone.utc)


def node(amount="123.45", currency="AUD", **extra):
    return {"id": GID, "name": "#SYNTHETIC", "legacyResourceId": "999999", "displayFinancialStatus": "PAID",
            "processedAt": "2026-11-05T01:00:00Z", "createdAt": "2026-11-05T01:00:00Z",
            "updatedAt": "2026-11-05T02:00:00Z",
            "totalPriceSet": {"shopMoney": {"amount": amount, "currencyCode": currency}}, **extra}


def daily(**extra):
    return {"account_id": "123", "ad_id": "ad1", "campaign_id": "c1",
            "date_start": "2026-11-05", "date_stop": "2026-11-05", "spend": "20",
            "impressions": "100", "clicks": "5", "actions": [{"action_type": "purchase", "value": "2"}],
            "action_values": [{"action_type": "purchase", "value": "100"}], **extra}


def reader(rows=None):
    result = Mock()
    result.get.return_value = copy.deepcopy(ACCOUNT)
    result.pages.return_value = [daily()] if rows is None else rows
    return result


def payload(rows=None):
    return sync.collect_reporting("2026-11-05", "2026-11-05", config=CONFIG, reader=reader(rows), at=AT)


class FinancialContractTests(unittest.TestCase):
    def test_required_money_in_every_order_query(self):
        for name in ("ORDERS_LIGHT_QUERY", "ORDERS_QUERY", "ORDERS_SAFE_QUERY", "ORDERS_BY_IDS_QUERY"):
            query = getattr(shopify_sync, name)
            self.assertIn("totalPriceSet", query)
            self.assertIn("currencyCode", query)

    def test_missing_distinct_from_explicit_complete_zero(self):
        self.assertEqual(graphql_financial_fields({}), {"_financial_fields_state": "missing"})
        for amount in (0, "0", "0.00"):
            normalized = shopify_sync.normalize_order(node(amount), "synthetic.myshopify.com")
            self.assertEqual(float(normalized["total_price"]), 0)
            self.assertEqual(normalized["_financial_fields_state"], "complete")
        for value in (None, {}, {"shopMoney": {"amount": "5"}}, {"shopMoney": {"amount": None, "currencyCode": "AUD"}}):
            normalized = graphql_financial_fields({"totalPriceSet": value})
            self.assertNotIn("total_price", normalized)
            self.assertNotIn("currency", normalized)

    def test_invalid_money_never_becomes_a_clearing_instruction(self):
        for amount, currency in (("", "AUD"), ("NaN", "AUD"), ("Infinity", "AUD"), (True, "AUD"), ("1", ""), ("1", None)):
            self.assertIsNone(money_pair(amount, currency))


class PreviewTests(unittest.TestCase):
    def captures(self):
        source = node()
        ledger = {"captured_at": AT.isoformat(), "rows": [{"shopify_order_id": GID, "total_price": "",
                   "currency": "", "remote_updated_at": source["updatedAt"], "protected_hash": "synthetic-hash"}]}
        provider = {"captured_at": AT.isoformat(), "rows": [source], "credential_context": "synthetic"}
        return ledger, provider

    def test_dry_run_is_repeatable_and_does_not_mutate_sources(self):
        ledger, provider = self.captures()
        before = copy.deepcopy((ledger, provider))
        first = repair.preview([GID], ledger, provider)
        self.assertEqual(first, repair.preview([GID], ledger, provider))
        self.assertEqual((ledger, provider), before)
        self.assertEqual(first["changes"][0]["status"], "proposed")
        self.assertFalse(first["apply_supported"])

    def test_missing_duplicate_unexpected_provider_rows_fail_closed(self):
        for nodes in ([], [None], [node(), node()], [node(id="gid://shopify/Order/1")]):
            ledger, provider = self.captures(); provider["rows"] = nodes
            with self.assertRaises(ValueError): repair.preview([GID], ledger, provider)

    def test_repaired_row_is_noop_and_conflicts_are_visible(self):
        ledger, provider = self.captures()
        ledger["rows"][0].update(total_price="123.45", currency="AUD")
        self.assertEqual(repair.preview([GID], ledger, provider)["changes"][0]["status"], "already_matches")
        ledger["rows"][0]["total_price"] = "123.4500"
        self.assertEqual(repair.preview([GID], ledger, provider)["changes"][0]["status"], "already_matches")
        ledger["rows"][0]["total_price"] = "999"
        self.assertIn("conflict", repair.preview([GID], ledger, provider)["changes"][0]["status"])
        ledger["rows"][0].update(total_price="", currency="", remote_updated_at="2026-11-06T00:00:00Z")
        self.assertEqual(repair.preview([GID], ledger, provider)["changes"][0]["status"], "blocked_stale_provider")

    def test_no_apply_cli(self):
        result = subprocess.run([sys.executable, "scripts/preview_order_financial_repair.py", "--apply"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(hasattr(repair, "apply"))


class ReportingReadTests(unittest.TestCase):
    def test_completed_account_days_and_provenance(self):
        result = sync.collect_reporting(days=7, config=CONFIG, reader=reader(), at=AT)
        self.assertEqual((result["reporting"]["since"], result["reporting"]["until"]), ("2026-10-30", "2026-11-05"))
        self.assertEqual(result["reporting"]["timezone"], "Australia/Sydney")
        self.assertEqual(result["reporting"]["action_report_time"], "impression")
        self.assertTrue(result["reporting"]["use_unified_attribution_setting"])

    def test_bad_account_incomplete_pagination_and_wrong_grain_never_save(self):
        for account in ({}, {**ACCOUNT, "account_id": "wrong"}, {**ACCOUNT, "currency": None}, {**ACCOUNT, "timezone_name": None}):
            test_reader = reader(); test_reader.get.return_value = account
            with self.assertRaises(ValueError):
                sync.collect_reporting(config=CONFIG, reader=test_reader, at=AT)
            test_reader.pages.assert_not_called()
        bad = reader(); bad.pages.side_effect = TimeoutError("partial page")
        with self.assertRaises(TimeoutError):
            sync.collect_reporting(config=CONFIG, reader=bad, at=AT)
        for row in (daily(account_id="other"), daily(date_stop="2026-11-06"), daily(date_start="2026-11-04")):
            with self.assertRaises(ValueError):
                sync.collect_reporting("2026-11-05", "2026-11-05", config=CONFIG, reader=reader([row]), at=AT)

    def test_completed_days_across_sydney_dst_and_invalid_ranges(self):
        from meta_reporting_contract import reporting_window
        for at, expected in (("2026-10-04T21:00:00+00:00", "2026-10-04"),
                             ("2026-04-05T22:00:00+00:00", "2026-04-05")):
            self.assertEqual(reporting_window(ACCOUNT, days=1, at=datetime.fromisoformat(at)), (expected, expected))
        for days in (True, 0, 32, 1.5, "7"):
            with self.assertRaises(ValueError): reporting_window(ACCOUNT, days=days, at=AT)

    def test_failure_then_retry_complete_does_not_persist_partial_read(self):
        bad = reader(); bad.pages.side_effect = TimeoutError("partial page")
        with patch.object(store, "log_start", return_value=1), patch.object(store, "log_failure") as failed, patch.object(store, "save_sync") as save:
            with self.assertRaises(RuntimeError):
                sync.sync_reporting("2026-11-05", "2026-11-05", config=CONFIG, reader=bad)
            save.assert_not_called(); failed.assert_called_once()
            save.return_value = {"daily": 1}
            self.assertEqual(sync.sync_reporting("2026-11-05", "2026-11-05", config=CONFIG, reader=reader())["counts"], {"daily": 1})
            self.assertEqual(save.call_count, 1)

    def test_no_deleted_filter_in_legacy_sync(self):
        fake = reader([])
        fake.pages.side_effect = lambda path, params: self.assertNotIn("DELETED", params.get("effective_status", "")) or []
        with patch.object(meta, "get_meta_config", return_value=CONFIG), patch.object(store, "log_start", return_value=1), patch.object(store, "save_sync", return_value={}), patch.object(store, "log_failure"):
            sync.sync("2026-11-05", "2026-11-05", assets=False, reader=fake)

    def test_existing_ui_performance_action_uses_persistent_daily_path(self):
        import ads_intelligence_page as page
        with patch.object(meta, "get_meta_config", return_value=CONFIG), patch.object(backend, "start_ads_sync_log", return_value=9), patch.object(backend, "finish_ads_sync_log"), patch.object(sync, "sync_reporting", return_value={"counts":{"accounts":1,"daily":1}, "warnings":[], "reporting":{"complete":True}}) as refreshed:
            result = page._sync_meta_ads("Last 7 days", 7)
        refreshed.assert_called_once_with(days=7, config=CONFIG)
        self.assertEqual(result["insights"], 1)
        self.assertEqual(result["status"], "success")


class NativeRepairTests(unittest.TestCase):
    """Actual SQL against temporary tables in the fixed disposable local database."""
    def setUp(self):
        self.conn = psycopg.connect("postgresql://postgres@127.0.0.1:15469/ai_restore_20261106?sslmode=disable", row_factory=dict_row)
        self.conn.execute("""CREATE TEMP TABLE shopify_orders(
            shopify_order_id text PRIMARY KEY,legacy_resource_id text,order_name text,shopify_order_name text,
            order_number text,shopify_order_number text,admin_url text,customer_id text,shopify_customer_id text,
            customer_name text,customer_email text,email text,financial_status text,fulfillment_status text,
            total_price text,currency text,created_at timestamptz,remote_updated_at timestamptz,
            processed_at timestamptz,cancelled_at timestamptz,raw_json jsonb,raw jsonb,synced_at timestamptz,updated_at timestamptz)""")
        self.conn.execute("""CREATE TEMP TABLE meta_ad_accounts(account_id text PRIMARY KEY,name text,currency text,
            timezone_name text,account_status text,business_name text,raw jsonb,synced_at timestamptz DEFAULT now(),updated_at timestamptz DEFAULT now())""")
        self.conn.execute("""CREATE TEMP TABLE ads_sync_logs(id bigserial PRIMARY KEY,source text,sync_type text,date_range text,
            context jsonb,started_at timestamptz DEFAULT now(),finished_at timestamptz,status text,rows_fetched int,rows_upserted int,error_message text)""")
        self.conn.execute("""CREATE TEMP TABLE ads_action_log(id bigserial PRIMARY KEY,action_type text,status text,
            summary text,context jsonb,created_at timestamptz DEFAULT now())""")
        self.conn.execute("""CREATE TEMP TABLE meta_ad_insights_daily(id bigserial,date date,account_id text,campaign_id text,
            campaign_name text,adset_id text,adset_name text,ad_id text,ad_name text,country text,placement text,raw jsonb,
            spend numeric,impressions int,clicks int,inline_link_clicks int,reach int,frequency numeric,cpc numeric,cpm numeric,
            purchases numeric,purchase_value numeric,roas numeric,add_to_cart numeric,ctr numeric,cost_per_purchase numeric,
            initiate_checkout numeric,synced_at timestamptz DEFAULT now(),updated_at timestamptz DEFAULT now(),
            UNIQUE(date,ad_id,country,placement))""")
        self.conn.commit()

        @contextmanager
        def cursor(write=False):
            with self.conn.transaction():
                with self.conn.cursor() as cur:
                    yield cur
        self.cursor_patch = patch.object(store, "cursor", cursor); self.cursor_patch.start()

    def tearDown(self):
        self.cursor_patch.stop(); self.conn.close()

    def put(self, source):
        normalized = shopify_sync.normalize_order(source, "synthetic.myshopify.com")
        with self.conn.cursor() as cur: backend._upsert_order(cur, normalized)
        self.conn.commit()

    def values(self):
        return self.conn.execute("SELECT total_price,currency,raw_json->>'total_price' raw_amount,raw->>'currency' raw_currency FROM shopify_orders").fetchone()

    def test_missing_invalid_and_repeat_snapshots_preserve_pair(self):
        self.put(node()); expected = self.values(); self.conn.commit()
        for price in (None, {}, {"shopMoney":{"amount":"999"}}, {"shopMoney":{"amount":"","currencyCode":"AUD"}}):
            self.put(node(totalPriceSet=price))
            self.assertEqual(self.values(), expected); self.conn.commit()
        bare = node(); del bare["totalPriceSet"]
        self.put(bare); self.put(bare)
        self.assertEqual(self.values(), expected)

    def test_explicit_zero_and_currency_change_but_stale_pair_rejected(self):
        self.put(node())
        self.put(node(0, "USD", updatedAt="2026-11-05T03:00:00Z"))
        self.assertEqual(self.values()["total_price"], "0"); self.conn.commit()
        self.put(node("999", "AUD", updatedAt="2026-11-05T01:00:00Z"))
        self.assertEqual(self.values(), {"total_price":"0","currency":"USD","raw_amount":"0","raw_currency":"USD"})
        self.conn.commit()
        # An older delivery must not move the freshness guard backwards and
        # allow a second, intermediate snapshot to replace the newest pair.
        self.put(node("777", "AUD", updatedAt="2026-11-05T02:00:00Z"))
        self.assertEqual(self.values()["total_price"], "0"); self.conn.commit()
        self.assertEqual(self.conn.execute("SELECT remote_updated_at FROM shopify_orders").fetchone()["remote_updated_at"], datetime(2026,11,5,3,tzinfo=timezone.utc))

    def test_webhook_shape_and_light_reconciliation_preserve_local_overrides(self):
        self.put(node())
        protected = {"_fulfilment_shipping_override": True, "shipping_method":"manual",
                     "shipping_carrier":"manual", "_orders_workflow_status":"hold", "_orders_refund":{"refund":"synthetic"}}
        self.conn.execute("UPDATE shopify_orders SET raw_json=raw_json||%s::jsonb,raw=raw||%s::jsonb", (json.dumps(protected),json.dumps(protected))); self.conn.commit()
        webhook = shopify_sync.normalize_order(node(), "synthetic.myshopify.com")
        webhook.update(total_price=0, currency="AUD")
        with self.conn.cursor() as cur: backend._upsert_order(cur, webhook)
        self.conn.commit()
        bare = node(); del bare["totalPriceSet"]
        self.put(bare)
        row = self.conn.execute("SELECT total_price,raw_json,raw FROM shopify_orders").fetchone()
        self.assertEqual(row["total_price"], "0")
        for field in ("raw_json", "raw"):
            self.assertEqual({key:row[field][key] for key in protected}, protected)

    def test_financial_preview_readonly_preserves_all_fields(self):
        self.put(node(totalPriceSet=None))
        before = self.conn.execute("SELECT md5(to_jsonb(o)::text) hash FROM shopify_orders o").fetchone()["hash"]; self.conn.commit()
        rows = repair.capture_ledger(self.conn, [GID]); self.conn.commit()
        result = repair.preview([GID], {"rows": rows, "captured_at": AT.isoformat()}, {"rows":[node()], "captured_at":AT.isoformat()})
        self.assertEqual(result["changes"][0]["status"], "proposed")
        self.assertEqual(before, self.conn.execute("SELECT md5(to_jsonb(o)::text) hash FROM shopify_orders o").fetchone()["hash"])

    def test_atomic_reporting_repeats_and_empty_refresh_preserve_other_grains(self):
        self.conn.execute("INSERT INTO meta_ad_insights_daily(date,account_id,ad_id,country,placement,spend) VALUES ('2026-11-05','123','ad1','AU','',99),('2026-11-05','other','other-ad','','',77)")
        self.conn.commit()
        for _ in range(2):
            log = store.log_start("123", "test"); store.save_sync(payload(), log)
        self.assertEqual(self.conn.execute("SELECT count(*) n FROM meta_ad_insights_daily").fetchone()["n"], 3); self.conn.commit()
        log = store.log_start("123", "empty"); store.save_sync(payload([]), log)
        self.assertEqual(self.conn.execute("SELECT count(*) n FROM meta_ad_insights_daily").fetchone()["n"], 2)

    def test_partial_database_failure_rolls_back_and_retry_recovers(self):
        first = store.log_start("123", "first"); store.save_sync(payload(), first)
        before = self.conn.execute("SELECT spend FROM meta_ad_insights_daily").fetchone(); self.conn.commit()
        next_log = store.log_start("123", "next")
        with patch.object(store.WriteBatch, "flush", side_effect=RuntimeError("simulated insert failure")):
            with self.assertRaises(RuntimeError): store.save_sync(payload([daily(spend="40")]), next_log)
        self.assertEqual(self.conn.execute("SELECT spend FROM meta_ad_insights_daily").fetchone(), before); self.conn.commit()
        store.save_sync(payload([daily(spend="40")]), next_log)
        self.assertEqual(self.conn.execute("SELECT spend FROM meta_ad_insights_daily").fetchone()["spend"], 40)

    def test_lost_acknowledgement_cannot_change_success_to_error(self):
        log = store.log_start("123", "first"); store.save_sync(payload(), log)
        store.log_failure(log, "lost acknowledgement")
        self.assertEqual(self.conn.execute("SELECT status FROM ads_sync_logs WHERE id=%s", (log,)).fetchone()["status"], "success")

    def test_conflicting_account_and_older_run_cannot_overwrite(self):
        older = store.log_start("123", "old")
        newer = store.log_start("123", "new"); store.save_sync(payload(), newer)
        with self.assertRaises(ValueError): store.save_sync(payload([daily(spend="99")]), older)
        different = payload([daily(ad_id="other-ad")])
        self.conn.execute("INSERT INTO meta_ad_insights_daily(date,account_id,ad_id,country,placement) VALUES ('2026-11-05','other','other-ad','','')")
        self.conn.commit()
        log = store.log_start("123", "conflict")
        with self.assertRaises(ValueError): store.save_sync(different, log)

    def test_legacy_failed_account_does_not_erase_metadata(self):
        log = store.log_start("123", "good"); store.save_sync(payload(), log)
        before = self.conn.execute("SELECT * FROM meta_ad_accounts").fetchone(); self.conn.commit()
        @contextmanager
        def connection():
            try:
                yield self.conn
            except Exception:
                self.conn.rollback()
                raise
        with patch.object(backend, "connect", connection), patch.object(backend, "ensure_ads_schema"), patch.object(backend, "set_app_setting"):
            backend.save_meta_ads_sync(account={}, account_id="act_123")
            self.assertEqual(self.conn.execute("SELECT * FROM meta_ad_accounts").fetchone(), before); self.conn.commit()
            backend.save_meta_ads_sync(account={"account_id":"123","currency":" ","timezone_name":None}, account_id="act_123")
        saved = self.conn.execute("SELECT currency,timezone_name,raw FROM meta_ad_accounts").fetchone()
        self.assertEqual((saved["currency"],saved["timezone_name"]), ("AUD","Australia/Sydney"))
        self.assertEqual((saved["raw"]["currency"],saved["raw"]["timezone_name"]), ("AUD","Australia/Sydney"))


if __name__ == "__main__":
    unittest.main()
