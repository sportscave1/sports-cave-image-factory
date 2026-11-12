import base64
import hmac
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import website_recommendation_analytics as analytics


ORIGIN = "https://www.sportscaveshop.com"


def payload(**changes):
    return {
        "event_id": str(uuid4()), "session_id": str(uuid4()), "event": "view",
        "placement": "desktop_menu", "market": "AU", "product_ids": ["100", "200"],
    } | changes


class RecommendationEvents(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(Starlette(routes=[
            Route(analytics.PATH, analytics.ingest, methods=["POST", "OPTIONS"]),
            Route(analytics.RANK_PATH, analytics.ranking, methods=["GET"]),
        ]))

    def test_accepted_event_never_persists_session_id(self):
        event = payload()
        with patch.object(analytics, "record") as save:
            response = self.client.post(analytics.PATH, json=event, headers={"Origin": ORIGIN})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["access-control-allow-origin"], ORIGIN)
        save.assert_called_once_with({key: value for key, value in event.items() if key != "session_id"})

    def test_rejects_invalid_origin_extra_fields_and_unconfirmed_placement(self):
        with patch.object(analytics, "record") as save:
            for headers, data, expected in (
                ({"Origin": "https://another.example"}, payload(), 403),
                ({"Origin": ORIGIN}, payload(email="synthetic@example.invalid"), 400),
                ({"Origin": ORIGIN}, payload(event="add_to_cart"), 400),
                ({"Origin": ORIGIN}, payload(placement="mobile_collector", event="click"), 400),
                ({"Origin": ORIGIN}, payload(product_ids=["1", "1"]), 400),
            ):
                self.assertEqual(self.client.post(analytics.PATH, json=data, headers=headers).status_code, expected)
        save.assert_not_called()

    def test_rate_limit_and_request_size(self):
        with patch.object(analytics, "record") as save, patch.object(analytics, "_allow_batch", return_value=False):
            self.assertEqual(self.client.post(analytics.PATH, json=payload(), headers={"Origin": ORIGIN}).status_code, 429)
            self.assertEqual(self.client.post(analytics.PATH, content=b"x" * 2049, headers={"Origin": ORIGIN}).status_code, 413)
        save.assert_not_called()

    @unittest.skipUnless(os.getenv("CRM_TEST_POSTGRES") == "1", "Disposable PostgreSQL fixture required")
    def test_sql_counts_products_and_deduplicates_retries(self):
        from crm_store import Store
        from tests.crm_db_fixture import connect

        store = Store(connect=connect)
        view = analytics.clean_event(payload(market="ZZ"))[1]
        add = analytics.clean_event(payload(event="add_to_cart", market="ZZ", placement="product_bundle", product_ids=["200"]))[1]
        try:
            analytics.record(view, store)
            analytics.record(view, store)
            analytics.record(add, store)
            rows = [row for row in analytics.report(store) if row["market"] == "ZZ"]
            self.assertEqual(rows, [
                {"market": "ZZ", "placement": "desktop_menu", "views": 2, "clicks": 0, "cart_adds": 0, "purchases": 0},
                {"market": "ZZ", "placement": "product_bundle", "views": 0, "clicks": 0, "cart_adds": 1, "purchases": 0},
            ])
        finally:
            store.q("DELETE FROM crm_runtime_state WHERE key IN (%s,%s)", tuple(
                analytics.PREFIX + event["event_id"] for event in (view, add)
            ))


    def test_ranking_is_market_scoped(self):
        with patch.object(analytics, "_ranking_snapshot", return_value={"AU": {"200": 2}, "US": {"300": 5}}):
            response = self.client.get(analytics.RANK_PATH + "?market=AU", headers={"Origin": ORIGIN})
            self.assertEqual(response.json(), {"scores": {"200": 2}})
            self.assertEqual(response.headers["access-control-allow-origin"], ORIGIN)
            self.assertEqual(self.client.get(analytics.RANK_PATH + "?market=aus").status_code, 400)
            self.assertEqual(self.client.get(analytics.RANK_PATH + "?market=AU", headers={"Origin": "https://another.example"}).status_code, 403)

    @unittest.skipUnless(os.getenv("CRM_TEST_POSTGRES") == "1", "Disposable PostgreSQL fixture required")
    def test_only_matching_paid_addons_count_and_feed_market_scores(self):
        from crm_store import Store
        from tests.crm_db_fixture import connect

        store = Store(connect=connect)
        events = [analytics.clean_event(payload(
            event="add_to_cart", market=market, placement="product_bundle", product_ids=["200"],
        ))[1] for market in ["ZX"] * 8 + ["ZY"]]
        event_ids = [event["event_id"] for event in events]

        def paid_order(event_id, product_id="200", **changes):
            return {"financial_status": "paid", "line_items": [{
                "product_id": product_id, "quantity": 1,
                "properties": [{"name": analytics.PROPERTY, "value": event_id}],
            }]} | changes

        orders = [paid_order(event_id) for event_id in (event_ids[0], event_ids[1], event_ids[-1])]
        orders += [paid_order(event_ids[2], "300"), paid_order(event_ids[3], test=True),
                   paid_order(event_ids[4], financial_status="pending")]
        try:
            for event in events:
                analytics.record(event, store)
            for order in orders + orders[:1]:
                analytics.record_paid_order(order, store)
            rows = {row["market"]: row for row in analytics.report(store)}
            self.assertEqual((rows["ZX"]["cart_adds"], rows["ZX"]["purchases"]), (8, 2))
            self.assertEqual(rows["ZY"]["purchases"], 1)
            scores = analytics.ranking_scores(store)
            self.assertEqual(scores["ZX"], {"200": 1})
            self.assertNotIn("ZY", scores)
        finally:
            for event_id in event_ids:
                store.q("DELETE FROM crm_runtime_state WHERE key IN (%s,%s,%s)", (
                    analytics.PREFIX + event_id,
                    f"{analytics.PAID_PREFIX}{event_id}/200",
                    f"{analytics.PAID_PREFIX}{event_id}/300",
                ))


    def test_paid_webhook_requires_a_valid_signature_and_durable_order(self):
        import webhook_server

        secret = uuid4().hex
        order = {"id": 123, "checkout_token": "fixture-checkout", "financial_status": "paid"}
        raw = json.dumps(order).encode()
        signature = base64.b64encode(hmac.digest(secret.encode(), raw, "sha256")).decode()
        endpoint = "/webhooks/shopify/orders-paid"
        client = TestClient(webhook_server.app)
        with (
            patch.dict(os.environ, {"SHOPIFY_WEBHOOK_SECRET": secret}, clear=True),
            patch("crm_store.Store"),
            patch("crm_webhooks.receive_shopify"),
            patch.object(analytics, "record_paid_order") as attribute,
            patch.object(webhook_server, "_process_paid_order_durably", return_value={"state": "duplicate"}) as persist,
        ):
            self.assertEqual(client.post(endpoint, content=raw, headers={"X-Shopify-Hmac-Sha256": "invalid"}).status_code, 401)
            persist.assert_not_called()
            attribute.assert_not_called()
            headers = {"X-Shopify-Hmac-Sha256": signature}
            persist.return_value = {"state": "receipt_failed"}
            self.assertEqual(client.post(endpoint, content=raw, headers=headers).status_code, 500)
            attribute.assert_not_called()
            persist.return_value = {"state": "duplicate"}
            self.assertEqual(client.post(endpoint, content=raw, headers=headers).status_code, 200)
            attribute.assert_called_once_with(order)
