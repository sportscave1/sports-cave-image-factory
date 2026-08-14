from datetime import date
from decimal import Decimal
import inspect
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import google_seo
import google_seo_phase4 as phase4
import os_accounts
import seo_page


ROOT = Path(__file__).resolve().parents[1]


def admin_user():
    return {
        "id": "admin-1",
        "display_name": "Nathan",
        "role": os_accounts.ROLE_ADMIN,
        "is_active": True,
    }


def worker_user():
    return {
        "id": "worker-1",
        "display_name": "Worker",
        "role": os_accounts.ROLE_WORKER,
        "is_active": True,
        "page_permissions": ["seo"],
    }


class ConnectionStore:
    def __init__(self):
        self.connection = {
            "encrypted_refresh_token": "encrypted-only",
            "has_refresh_token": True,
            "gsc_site_url": "https://example.test/",
            "ga4_property_id": "properties/123",
            "ga4_property_currency": "AUD",
            "connection_status": "Connected",
        }

    def get_connection_secret(self):
        return dict(self.connection)

    def get_connection(self):
        return dict(self.connection)


class MemoryPhase4Store:
    def __init__(self, *, run=None, bounds=(date(2026, 8, 1), date(2026, 8, 10))):
        self.run = dict(run or {})
        self.bounds = bounds
        self.claimed = False
        self.queued = []
        self.transactions = {}
        self.checkpoints = []
        self.completed = None

    def phase3_health(self):
        return {
            "GSC": {"latest_stored_date": "2026-08-10", "duplicate_active": False},
            "GA4": {"latest_stored_date": "2026-08-10", "duplicate_active": False},
        }

    def queue_run(self, source, mode, **values):
        active = next((row for row in self.queued if row["source"] == source), None)
        if active:
            return dict(active)
        row = {"id": f"run-{source}", "source": source, "mode": mode, "status": "queued", **values}
        self.queued.append(row)
        return dict(row)

    def claim_next_run(self, _worker_id, *, source=""):
        if self.claimed or not self.run or (source and source != self.run.get("source")):
            return None
        self.claimed = True
        return dict(self.run)

    def ga4_completed_bounds(self, _property_id):
        return self.bounds

    def renew_lease(self, *_args, **_kwargs):
        return True

    def replace_ga4_transactions_date(self, _property_id, slice_data):
        day = slice_data["date"]
        previous = len(self.transactions.get(day, []))
        self.transactions[day] = list(slice_data["rows"])
        return {"inserted": len(slice_data["rows"]), "replaced": previous}

    def checkpoint_run(self, _run_id, _lease_owner, **values):
        self.checkpoints.append(values)

    def save_source_state(self, *_args, **_kwargs):
        return None

    def complete_run(self, run_id, _lease_owner, *, status="completed"):
        self.completed = {"id": run_id, "status": status}
        return dict(self.completed)

    def fail_run(self, run_id, _lease_owner, error, *, partial=False):
        return {"id": run_id, "status": "partial" if partial else "failed", "error": error.code}

    def refresh_health(self):
        return {}


class URLNormalizationTests(unittest.TestCase):
    def test_normalizes_transport_www_slashes_trailing_query_and_fragment(self):
        normalized = phase4.normalize_seo_url(
            "http://WWW.Example.com:80//products/hero/?utm_source=x#detail"
        )
        self.assertTrue(normalized["valid"])
        self.assertEqual(normalized["normalized_url"], "https://example.com/products/hero")
        self.assertEqual(normalized["query_string"], "utm_source=x")

    def test_decodes_only_unreserved_characters(self):
        normalized = phase4.normalize_seo_url("https://example.test/pages/the%2Dhero%2Fstory")
        self.assertEqual(normalized["normalized_path"], "/pages/the-hero%2Fstory")

    def test_unicode_and_spaces_use_stable_percent_encoding(self):
        normalized = phase4.normalize_seo_url("https://example.test/pages/café hero")
        self.assertEqual(normalized["normalized_path"], "/pages/caf%C3%A9%20hero")

    def test_invalid_and_not_set_landing_pages_remain_unmapped(self):
        self.assertFalse(phase4.normalize_seo_url("(not set)", primary_host="example.test")["valid"])
        self.assertFalse(phase4.normalize_seo_url("/page")["valid"])

    def test_shopify_canonical_page_matches_exact_alias(self):
        page = phase4.canonical_page_from_shopify(
            {
                "page_type": "product",
                "shopify_resource_id": "gid://shopify/Product/1",
                "handle": "hero",
                "canonical_url": "https://www.example.test/products/hero/",
                "title": "Hero",
            },
            primary_host="example.test",
        )
        alias = phase4.normalize_seo_url("http://example.test/products/hero?variant=1")
        result = phase4.map_alias_to_pages(alias, [page])
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["page_key"], page["page_key"])

    def test_known_locale_paths_match_unique_canonical_shopify_path(self):
        page = phase4.canonical_page_from_shopify(
            {
                "page_type": "product",
                "shopify_resource_id": "gid://shopify/Product/1",
                "handle": "hero",
                "canonical_url": "https://example.test/products/hero",
            },
            primary_host="example.test",
            known_locale_prefixes=("en-au",),
        )
        alias = phase4.normalize_seo_url(
            "https://example.test/en-au/products/hero",
            known_locale_prefixes=("en-au",),
        )
        result = phase4.map_alias_to_pages(alias, [page])
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["method"], "unique_canonical_path")

    def test_unknown_locale_paths_are_not_blindly_merged(self):
        page = phase4.canonical_page_from_shopify(
            {
                "page_type": "product",
                "shopify_resource_id": "gid://shopify/Product/1",
                "handle": "hero",
                "canonical_url": "https://example.test/products/hero",
            },
            primary_host="example.test",
            known_locale_prefixes=("en-au",),
        )
        alias = phase4.normalize_seo_url(
            "https://example.test/fr-fr/products/hero",
            known_locale_prefixes=("en-au",),
        )
        result = phase4.map_alias_to_pages(alias, [page])
        self.assertEqual(result["status"], "unmapped")


class MetricsAndFilterTests(unittest.TestCase):
    def test_ctr_and_position_use_correct_weighting(self):
        result = phase4.aggregate_gsc_rows(
            [
                {"clicks": 1, "impressions": 10, "average_position": 2},
                {"clicks": 9, "impressions": 90, "average_position": 10},
            ]
        )
        self.assertEqual(result["ctr"], Decimal("0.1"))
        self.assertEqual(result["average_position"], Decimal("9.2"))

    def test_previous_period_is_immediately_preceding_and_equal_length(self):
        period = phase4.reporting_period("Last 28 days", through_date=date(2026, 8, 12))
        self.assertEqual((period.start_date, period.end_date), (date(2026, 7, 16), date(2026, 8, 12)))
        self.assertEqual((period.previous_start_date, period.previous_end_date), (date(2026, 6, 18), date(2026, 7, 15)))

    def test_market_device_and_brand_filters_are_explicit(self):
        period = phase4.reporting_period("Last 28 days", through_date=date(2026, 8, 12))
        filters = phase4.ReportingFilters(period, market="Australia", device="Mobile", search="Brand")
        self.assertEqual(filters.country_values(), {"AU", "AUS"})
        self.assertEqual(filters.device_values(), {"mobile", "MOBILE"})
        self.assertTrue(phase4.classify_brand_query("Sports Cave Jordan art", ["sports cave"]))
        self.assertFalse(phase4.classify_brand_query("Jordan wall art", ["sports cave"]))

    def test_reporting_sql_aggregates_sources_before_join(self):
        source = inspect.getsource(phase4.PostgresSEOReportingReader._top_pages)
        self.assertIn("seo_reporting_landing_page_daily", source)
        self.assertIn("seo_reporting_landing_page_revenue_daily", source)
        self.assertNotIn("seo_gsc_daily_details AS gsc JOIN seo_ga4", source)

    def test_overview_reader_uses_persisted_reporting_snapshots(self):
        source = "\n".join(
            (
                inspect.getsource(phase4.PostgresSEOReportingReader._period_metrics),
                inspect.getsource(phase4.PostgresSEOReportingReader._daily_trend),
                inspect.getsource(phase4.PostgresSEOReportingReader._top_queries),
            )
        )
        self.assertIn("seo_reporting_daily_metrics", source)
        self.assertIn("seo_reporting_revenue_daily", source)
        self.assertIn("seo_reporting_query_daily", source)
        self.assertNotIn("seo_gsc_daily_totals", source)
        self.assertNotIn("seo_ga4_daily_landing_pages", source)

    def test_reporting_snapshot_refresh_is_database_only(self):
        source = inspect.getsource(phase4.PostgresSEOPhase4Store.refresh_reporting_snapshots)
        self.assertIn("seo_reporting_daily_metrics", source)
        for forbidden in ("ShopifySEOClient", "GoogleSEOReportingClient", "requests.get", "requests.post"):
            self.assertNotIn(forbidden, source)


class RevenueReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.transaction = {"transaction_id": "#SC3001", "attributed_purchase_revenue": "120", "currency": "AUD"}
        self.order = {
            "shopify_order_id": "gid://shopify/Order/3001",
            "net_revenue": "110",
            "currency": "AUD",
        }

    def test_exact_match_confirms_shopify_as_revenue_source_of_truth(self):
        result = phase4.reconcile_transaction(self.transaction, [self.order])
        self.assertEqual(result["state"], "confirmed_shopify_match")
        self.assertEqual(result["ga4_attributed_revenue"], Decimal("120"))
        self.assertEqual(result["shopify_confirmed_revenue"], Decimal("110"))

    def test_unmatched_duplicate_refund_cancel_and_test_states(self):
        self.assertEqual(phase4.reconcile_transaction(self.transaction, [])["state"], "ga4_transaction_unmatched")
        duplicate = {**self.order, "shopify_order_id": "another"}
        self.assertEqual(
            phase4.reconcile_transaction(self.transaction, [self.order, duplicate])["state"],
            "duplicate_or_conflicting_transaction",
        )
        cases = (
            ("is_test", "excluded_test_order"),
            ("is_cancelled", "excluded_cancelled_order"),
            ("is_fully_refunded", "excluded_fully_refunded_order"),
        )
        for flag, expected in cases:
            with self.subTest(flag=flag):
                self.assertEqual(phase4.reconcile_transaction(self.transaction, [{**self.order, flag: True}])["state"], expected)

    def test_currency_mismatch_is_not_confirmed(self):
        result = phase4.reconcile_transaction(self.transaction, [{**self.order, "currency": "USD"}])
        self.assertEqual(result["state"], "currency_mismatch")
        self.assertEqual(result["shopify_confirmed_revenue"], Decimal("0"))

    def test_public_reconciliation_status_separates_confirmed_unmatched_and_disputed(self):
        confirmed = phase4.public_reconciliation_status(
            phase4.reconcile_transaction(self.transaction, [self.order])
        )
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(confirmed["shopify_order_count"], 1)
        unmatched = phase4.public_reconciliation_status(
            phase4.reconcile_transaction(self.transaction, [])
        )
        self.assertEqual(unmatched["status"], "unmatched")
        disputed = phase4.public_reconciliation_status(
            phase4.reconcile_transaction(self.transaction, [{**self.order, "currency": "USD"}])
        )
        self.assertEqual(disputed["status"], "disputed")

    def test_conflicting_ga4_transaction_is_never_confirmed(self):
        result = phase4.reconcile_transaction(
            {**self.transaction, "conflict_state": "duplicate_across_dates"},
            [self.order],
        )
        self.assertEqual(result["state"], "duplicate_or_conflicting_transaction")
        self.assertEqual(result["shopify_confirmed_revenue"], Decimal("0"))

    def test_matching_uses_identifiers_and_never_amounts(self):
        source = inspect.getsource(phase4.reconcile_transaction)
        self.assertNotIn("gross_revenue ==", source)
        self.assertNotIn("attributed_purchase_revenue ==", source)
        keys = phase4.transaction_match_keys("#SC3001")
        self.assertEqual(keys, ["#sc3001", "sc3001"])


class FakeGoogleClient:
    def __init__(self, _access_token):
        self.calls = []

    def _post(self, _url, payload, *, stage):
        self.calls.append((payload, stage))
        if stage == "ga4_transaction_compatibility":
            return {
                "dimensionCompatibilities": [
                    {"dimensionMetadata": {"apiName": name}, "compatibility": "COMPATIBLE"}
                    for name in (*phase4.GA4_TRANSACTION_REQUIRED_DIMENSIONS, phase4.GA4_TRANSACTION_OPTIONAL_DIMENSION)
                ],
                "metricCompatibilities": [
                    {"metricMetadata": {"apiName": name}, "compatibility": "COMPATIBLE"}
                    for name in phase4.GA4_TRANSACTION_METRICS
                ],
            }
        day = payload["dateRanges"][0]["startDate"]
        return {
            "rowCount": 1,
            "dimensionHeaders": [
                {"name": "date"}, {"name": "transactionId"},
                {"name": "landingPagePlusQueryString"}, {"name": "hostname"},
                {"name": "countryId"}, {"name": "deviceCategory"},
                {"name": "sessionDefaultChannelGroup"},
            ],
            "metricHeaders": [{"name": "transactions"}, {"name": "purchaseRevenue"}],
            "rows": [{
                "dimensionValues": [
                    {"value": day.replace("-", "")}, {"value": "#SC3001"},
                    {"value": "/products/hero"}, {"value": "example.test"},
                    {"value": "AU"}, {"value": "desktop"}, {"value": "Organic Search"},
                ],
                "metricValues": [{"value": "1"}, {"value": "120"}],
            }],
            "metadata": {"currencyCode": "AUD"},
        }


class TransactionPaginationClient:
    def __init__(self):
        self.offsets = []

    def _post(self, _url, payload, *, stage):
        self.assert_stage = stage
        offset = int(payload["offset"])
        self.offsets.append(offset)
        transaction_id = "#SC3001" if offset == 0 else "#SC3002"
        return {
            "rowCount": 2,
            "dimensionHeaders": [
                {"name": "date"}, {"name": "transactionId"},
                {"name": "landingPagePlusQueryString"}, {"name": "hostname"},
                {"name": "countryId"}, {"name": "deviceCategory"},
                {"name": "sessionDefaultChannelGroup"},
            ],
            "metricHeaders": [{"name": "transactions"}, {"name": "purchaseRevenue"}],
            "rows": [{
                "dimensionValues": [
                    {"value": "20260810"}, {"value": transaction_id},
                    {"value": "/products/hero"}, {"value": "example.test"},
                    {"value": "AU"}, {"value": "desktop"}, {"value": "Organic Search"},
                ],
                "metricValues": [{"value": "1"}, {"value": "100"}],
            }],
            "metadata": {"currencyCode": "AUD"},
        }


class APIContractTests(unittest.TestCase):
    def test_ga4_transaction_rows_paginate_to_reported_row_count(self):
        client = TransactionPaginationClient()
        result = phase4.fetch_ga4_transactions_date(
            client,
            "properties/123",
            date(2026, 8, 10),
        )
        self.assertEqual(client.offsets, [0, 1])
        self.assertEqual({row["transaction_id"] for row in result["rows"]}, {"#SC3001", "#SC3002"})


class WorkerAndSecurityTests(unittest.TestCase):
    def test_queue_is_admin_only_and_idempotent_per_source(self):
        store = MemoryPhase4Store()
        connection = ConnectionStore()
        with patch.object(phase4, "record_activity_log"):
            first = phase4.queue_phase4_pipeline(admin_user(), "historical", phase4_store=store, connection_store=connection)
            second = phase4.queue_phase4_pipeline(admin_user(), "historical", phase4_store=store, connection_store=connection)
        self.assertEqual(len(store.queued), len(phase4.PHASE4_SOURCES))
        self.assertEqual(first, second)
        with self.assertRaises(PermissionError):
            phase4.queue_phase4_pipeline(worker_user(), "historical", phase4_store=store, connection_store=connection)

    def test_partial_phase3_history_imports_only_completed_dates_and_resumes_checkpoint(self):
        run = {
            "id": "run-ga4",
            "source": "ga4_transactions",
            "mode": "historical",
            "status": "running",
            "checkpoint_date": date(2026, 8, 8),
        }
        store = MemoryPhase4Store(run=run)
        client = FakeGoogleClient("")
        worker = phase4.SEOPhase4Worker(
            phase4_store=store,
            connection_store=ConnectionStore(),
            config_loader=lambda: {},
            access_token_loader=lambda *_args: ("access", ConnectionStore().connection),
            google_client_factory=lambda _token: client,
        )
        result = worker.run_once()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(sorted(store.transactions), [date(2026, 8, 9), date(2026, 8, 10)])

    def test_manual_transaction_refresh_rechecks_previous_seven_completed_days(self):
        run = {"id": "run-ga4", "source": "ga4_transactions", "mode": "manual", "status": "running"}
        store = MemoryPhase4Store(run=run)
        worker = phase4.SEOPhase4Worker(
            phase4_store=store,
            connection_store=ConnectionStore(),
            config_loader=lambda: {},
            access_token_loader=lambda *_args: ("access", ConnectionStore().connection),
            google_client_factory=FakeGoogleClient,
        )
        worker.run_once()
        self.assertEqual(
            sorted(store.transactions),
            [date(2026, 8, day) for day in range(4, 11)],
        )

    def test_migration_and_source_never_store_customer_pii_or_secrets(self):
        sql = (ROOT / "migrations" / phase4.PHASE4_MIGRATION).read_text(encoding="utf-8").casefold()
        source = (ROOT / "google_seo_phase4.py").read_text(encoding="utf-8").casefold()
        for forbidden in ("customer_email", "shipping_address", "billing_address", "access_token text", "refresh_token text"):
            self.assertNotIn(forbidden, sql)
        self.assertNotIn("customer {", source)

    def test_shopify_and_reconciliation_writes_are_idempotent(self):
        canonical_source = inspect.getsource(phase4.PostgresSEOPhase4Store.upsert_canonical_pages)
        order_source = inspect.getsource(phase4.PostgresSEOPhase4Store.upsert_shopify_order_facts)
        reconciliation_source = inspect.getsource(phase4.PostgresSEOPhase4Store.reconcile_revenue)
        self.assertIn("ON CONFLICT (workspace_key, page_type, shopify_resource_id)", canonical_source)
        self.assertIn("ON CONFLICT (workspace_key, shopify_order_id)", order_source)
        self.assertIn(
            "ON CONFLICT (workspace_key, ga4_property_id, transaction_id, transaction_date)",
            reconciliation_source,
        )

    def test_manual_url_mappings_survive_automatic_mapping_refresh(self):
        source = inspect.getsource(phase4.PostgresSEOPhase4Store.map_saved_urls)
        self.assertIn("manual_override=TRUE", source)
        self.assertIn("CASE WHEN seo_url_aliases.manual_override", source)
        self.assertIn("manual_aliases.get", source)

    def test_phase4_jobs_use_expiring_leases_and_dependency_order(self):
        source = inspect.getsource(phase4.PostgresSEOPhase4Store.claim_next_run)
        self.assertIn("FOR UPDATE SKIP LOCKED", source)
        self.assertIn("lease_expires_at", source)
        self.assertIn("source<>'mapping'", source)
        self.assertIn("source<>'reconciliation'", source)

    def test_overview_phase4_foundation_uses_saved_data_only(self):
        source = inspect.getsource(seo_page._render_phase4_foundation)
        for forbidden in ("ShopifySEOClient", "GoogleSEOReportingClient", "graphql_request", "requests.get", "requests.post"):
            self.assertNotIn(forbidden, source)

    def test_phase4_cards_do_not_show_zero_success_before_rows_are_evaluated(self):
        source = inspect.getsource(seo_page._render_phase4_foundation)
        self.assertIn("No source URLs processed", source)
        self.assertIn("No GA4 transactions evaluated", source)


if __name__ == "__main__":
    unittest.main()
