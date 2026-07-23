import base64
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from PIL import Image
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import collector_vault
import collector_vault_api


ROOT = Path(__file__).resolve().parents[1]
CUSTOMER_A = "gid://shopify/Customer/101"
CUSTOMER_B = "gid://shopify/Customer/202"
SHOP_DOMAIN = "sports-cave.myshopify.com"
CLIENT_ID = "collector-vault-client"
SECRET = "collector-vault-test-secret"


def _segment(value):
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _session_token(*, customer=CUSTOMER_A, expires_in=300, audience=CLIENT_ID):
    now = int(time.time())
    header = _segment({"alg": "HS256", "typ": "JWT"})
    payload = _segment(
        {
            "aud": audience,
            "dest": f"https://{SHOP_DOMAIN}",
            "exp": now + expires_in,
            "iat": now,
            "nbf": now,
            "sub": customer,
        }
    )
    signature = hmac.new(
        SECRET.encode("utf-8"),
        f"{header}.{payload}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{header}.{payload}.{encoded_signature}"


def _certificate_row(customer=CUSTOMER_A):
    return {
        "certificate_row_id": 12,
        "order_customer_id": customer,
        "certificate_customer_id": customer,
        "shopify_order_id": "gid://shopify/Order/44",
        "shopify_order_name": "#1044",
        "shopify_product_id": "gid://shopify/Product/55",
        "shopify_variant_id": "gid://shopify/ProductVariant/66",
        "product_title": "The Mountain Chooses",
        "edition_number": 27,
        "edition_limit": 100,
        "certificate_id": "SC-1044-027",
        "purchase_date": "2026-06-29T10:00:00Z",
        "certificate_pdf_url": "https://cdn.example.com/certificate.pdf",
        "certificate_preview_image_url": "https://cdn.example.com/preview.png",
    }


class CollectorVaultAuthenticationTests(unittest.TestCase):
    def test_valid_shopify_session_token_is_verified(self):
        result = collector_vault.verify_shopify_session_token(
            _session_token(),
            secret_candidates=[SECRET],
            audience=CLIENT_ID,
            shop_domain=SHOP_DOMAIN,
        )
        self.assertEqual(result["shopify_customer_id"], CUSTOMER_A)
        self.assertEqual(result["shop_domain"], SHOP_DOMAIN)

    def test_expired_wrong_audience_and_tampered_tokens_are_rejected(self):
        scenarios = [
            _session_token(expires_in=-120),
            _session_token(audience="another-app"),
            _session_token()[:-1] + "x",
        ]
        for token in scenarios:
            with self.subTest(token=token[-12:]):
                with self.assertRaises(collector_vault.CollectorVaultAuthenticationError):
                    collector_vault.verify_shopify_session_token(
                        token,
                        secret_candidates=[SECRET],
                        audience=CLIENT_ID,
                        shop_domain=SHOP_DOMAIN,
                    )

    def test_certificate_reference_cannot_cross_customers(self):
        with patch.dict(
            os.environ,
            {"COLLECTOR_VAULT_ASSET_SIGNING_SECRET": SECRET},
            clear=False,
        ):
            reference = collector_vault._signed_token(
                {
                    "purpose": "certificate",
                    "certificate_row_id": 12,
                    "customer_hash": collector_vault.customer_hash(CUSTOMER_A),
                },
                ttl_seconds=300,
            )
            with patch.object(collector_vault, "list_owned_certificates") as owned:
                with self.assertRaises(collector_vault.CollectorVaultAuthorizationError):
                    collector_vault._resolve_certificate_reference(reference, CUSTOMER_B)
                owned.assert_not_called()

    def test_owned_certificate_is_resolved_by_database_row_not_browser_metadata(self):
        row = _certificate_row()
        with patch.dict(
            os.environ,
            {"COLLECTOR_VAULT_ASSET_SIGNING_SECRET": SECRET},
            clear=False,
        ):
            reference = collector_vault._signed_token(
                {
                    "purpose": "certificate",
                    "certificate_row_id": 12,
                    "customer_hash": collector_vault.customer_hash(CUSTOMER_A),
                },
                ttl_seconds=300,
            )
            with patch.object(collector_vault, "list_owned_certificates", return_value=[row]):
                resolved = collector_vault._resolve_certificate_reference(reference, CUSTOMER_A)
        self.assertEqual(resolved["certificate_id"], "SC-1044-027")


class CollectorVaultEligibilityTests(unittest.TestCase):
    def _order(self, shipment_status, *, display="FULFILLED", fulfillment_status="SUCCESS"):
        return {
            "id": "gid://shopify/Order/44",
            "customer": {"id": CUSTOMER_A},
            "displayFulfillmentStatus": display,
            "fulfillments": [
                {
                    "status": fulfillment_status,
                    "events": {
                        "nodes": (
                            [{"status": shipment_status, "happenedAt": "2026-07-01T00:00:00Z"}]
                            if shipment_status
                            else []
                        )
                    },
                }
            ],
        }

    def test_only_confirmed_delivery_is_review_eligible(self):
        self.assertTrue(collector_vault._is_delivered_order(self._order("DELIVERED"), CUSTOMER_A))
        for status in ("IN_TRANSIT", "OUT_FOR_DELIVERY", "LABEL_PRINTED", "PICKED_UP", None):
            with self.subTest(status=status):
                self.assertFalse(
                    collector_vault._is_delivered_order(self._order(status), CUSTOMER_A)
                )
        self.assertFalse(
            collector_vault._is_delivered_order(
                self._order("DELIVERED", display="UNFULFILLED"),
                CUSTOMER_A,
            )
        )
        self.assertFalse(
            collector_vault._is_delivered_order(self._order("DELIVERED"), CUSTOMER_B)
        )

    def test_review_prompt_uses_newest_delivered_unreviewed_mapped_purchase(self):
        row = _certificate_row()
        with (
            patch.dict(
                os.environ,
                {
                    "COLLECTOR_VAULT_ASSET_SIGNING_SECRET": SECRET,
                    "JUDGEME_PRIVATE_API_TOKEN": "private-test-token",
                },
                clear=False,
            ),
            patch.object(
                collector_vault,
                "delivery_statuses",
                return_value={"gid://shopify/Order/44": True},
            ),
            patch.object(collector_vault, "_reviewed_keys", return_value=set()),
            patch.object(
                collector_vault,
                "lookup_judgeme_product",
                return_value={"id": "99", "external_id": "55"},
            ),
        ):
            prompt = collector_vault.review_prompt([row], CUSTOMER_A)
        self.assertEqual(prompt["shopify_product_id"], "gid://shopify/Product/55")
        self.assertEqual(prompt["product_title"], "The Mountain Chooses")

    def test_review_prompt_is_hidden_after_submission_or_without_delivery(self):
        row = _certificate_row()
        reviewed = {
            ("gid://shopify/Order/44", "gid://shopify/Product/55"),
        }
        with (
            patch.dict(
                os.environ,
                {
                    "COLLECTOR_VAULT_ASSET_SIGNING_SECRET": SECRET,
                    "JUDGEME_PRIVATE_API_TOKEN": "private-test-token",
                },
                clear=False,
            ),
            patch.object(
                collector_vault,
                "delivery_statuses",
                return_value={"gid://shopify/Order/44": True},
            ),
            patch.object(collector_vault, "_reviewed_keys", return_value=reviewed),
        ):
            self.assertIsNone(collector_vault.review_prompt([row], CUSTOMER_A))
        with (
            patch.dict(
                os.environ,
                {
                    "COLLECTOR_VAULT_ASSET_SIGNING_SECRET": SECRET,
                    "JUDGEME_PRIVATE_API_TOKEN": "private-test-token",
                },
                clear=False,
            ),
            patch.object(collector_vault, "delivery_statuses", return_value={}),
            patch.object(collector_vault, "_reviewed_keys", return_value=set()),
        ):
            self.assertIsNone(collector_vault.review_prompt([row], CUSTOMER_A))

    def test_delivery_lookup_is_batched_and_cached(self):
        collector_vault._DELIVERY_CACHE.clear()
        response = {
            "nodes": [
                {
                    "id": "gid://shopify/Order/44",
                    "customer": {"id": CUSTOMER_A},
                    "displayFulfillmentStatus": "FULFILLED",
                    "fulfillments": [
                        {
                            "status": "SUCCESS",
                            "events": {
                                "nodes": [
                                    {
                                        "status": "DELIVERED",
                                        "happenedAt": "2026-07-01T00:00:00Z",
                                    }
                                ]
                            },
                        }
                    ],
                }
            ]
        }
        with (
            patch.dict(
                os.environ,
                {"COLLECTOR_VAULT_ASSET_SIGNING_SECRET": SECRET},
                clear=False,
            ),
            patch.object(
                collector_vault.shopify_sync,
                "graphql_request",
                return_value=(response, "2026-04"),
            ) as request,
        ):
            first = collector_vault.delivery_statuses(["44", "44"], CUSTOMER_A)
            second = collector_vault.delivery_statuses(["44"], CUSTOMER_A)
        self.assertTrue(first["gid://shopify/Order/44"])
        self.assertEqual(first, second)
        request.assert_called_once()


class CollectorVaultReviewTests(unittest.TestCase):
    def _photo_payload(self, image_format="JPEG", mime_type="image/jpeg"):
        image = Image.new("RGB", (12, 8), "red")
        buffer = io.BytesIO()
        image.save(buffer, image_format)
        return {
            "mime_type": mime_type,
            "filename": "room.jpg",
            "base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
        }

    def test_review_photo_accepts_images_and_reencodes_them(self):
        result = collector_vault.validate_review_photo(self._photo_payload())
        self.assertEqual(result["mime_type"], "image/jpeg")
        self.assertEqual(result["extension"], ".jpg")
        with Image.open(io.BytesIO(result["bytes"])) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (12, 8))

    def test_review_photo_rejects_bad_mime_content_and_oversize(self):
        with self.assertRaises(collector_vault.CollectorVaultError):
            collector_vault.validate_review_photo(
                {"mime_type": "image/svg+xml", "base64": base64.b64encode(b"<svg/>").decode()}
            )
        with self.assertRaises(collector_vault.CollectorVaultError):
            collector_vault.validate_review_photo(
                {
                    "mime_type": "image/png",
                    "base64": self._photo_payload()["base64"],
                }
            )
        with (
            patch.dict(os.environ, {"COLLECTOR_VAULT_REVIEW_PHOTO_MAX_BYTES": "8"}),
            self.assertRaises(collector_vault.CollectorVaultError),
        ):
            collector_vault.validate_review_photo(self._photo_payload())

    def test_judgeme_submission_maps_by_stable_shopify_product_id(self):
        captured = {}

        class Response:
            status_code = 200
            content = b"{}"

            @staticmethod
            def json():
                return {"review": {"id": 88}}

        def post(url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return Response()

        with (
            patch.dict(
                os.environ,
                {
                    "JUDGEME_PRIVATE_API_TOKEN": "private-token",
                    "JUDGEME_SHOP_DOMAIN": SHOP_DOMAIN,
                },
                clear=False,
            ),
            patch.object(
                collector_vault,
                "lookup_judgeme_product",
                return_value={"id": "9", "external_id": "55"},
            ),
        ):
            result = collector_vault._submit_judgeme_review(
                _certificate_row(),
                {"rating": 5, "review_body": "Looks superb on the wall.", "review_title": "Superb"},
                name="Collector",
                email="collector@example.com",
                photo_upload={},
                request_post=post,
            )
        self.assertEqual(captured["json"]["id"], "55")
        self.assertNotIn("product_title", captured["json"])
        self.assertEqual(result["review_id"], "88")

    def test_review_text_is_plain_text_safe(self):
        cleaned = collector_vault._clean_review_text(
            'Great print <script>alert("x")</script>',
            maximum=2000,
        )
        self.assertNotIn("<script>", cleaned)
        self.assertIn("&lt;script&gt;", cleaned)


class CollectorVaultApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Starlette(
            routes=[
                Route(path, endpoint, methods=list(methods))
                for path, endpoint, methods in collector_vault_api.COLLECTOR_VAULT_ROUTES
            ]
        )

    def test_preflight_is_allowed_without_authentication(self):
        response = TestClient(self.app).options(
            "/api/collector-vault/review",
            headers={
                "Origin": "https://shopify.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["access-control-allow-origin"], "*")

    def test_customer_error_does_not_expose_internal_detail(self):
        response = TestClient(self.app).get("/api/collector-vault/bootstrap")
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("detail", response.json())
        self.assertIn("error", response.json())

    def test_post_requires_csrf_marker_and_signed_session(self):
        response = TestClient(self.app).post(
            "/api/collector-vault/events",
            headers={"Authorization": f"Bearer {_session_token()}"},
            json={"event": "collection_viewed"},
        )
        self.assertEqual(response.status_code, 403)

    def test_download_filename_preserves_unicode_without_header_injection(self):
        filename = collector_vault._certificate_filename(
            {
                "product_title": 'André "The Ace"\r\nWall Art',
                "edition_number": 7,
            },
            "pdf",
        )
        header = collector_vault_api._content_disposition(
            {"kind": "pdf", "filename": filename}
        )
        self.assertIn("filename*=UTF-8''Andr%C3%A9", header)
        self.assertNotIn("\r", header)
        self.assertNotIn("\n", header)


class CollectorVaultImplementationTests(unittest.TestCase):
    def test_migration_is_additive_server_only_and_idempotent(self):
        source = (ROOT / "migrations" / "20260723_collector_vault.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS collector_frame_requests", source)
        self.assertIn("CREATE TABLE IF NOT EXISTS collector_reviews", source)
        self.assertIn("UNIQUE (customer_hash, certificate_row_id, idempotency_key)", source)
        self.assertIn("UNIQUE (customer_hash, shopify_order_id, shopify_product_id)", source)
        self.assertIn("ENABLE ROW LEVEL SECURITY", source)
        self.assertNotIn("DROP TABLE", source.upper())

    def test_certificate_query_enforces_order_and_certificate_customer_ownership(self):
        source = (ROOT / "collector_vault.py").read_text(encoding="utf-8")
        self.assertIn("WHERE o.customer_id = ANY(%s)", source)
        self.assertIn("c.shopify_customer_id = ANY(%s)", source)
        self.assertIn("eo.shopify_customer_id = ANY(%s)", source)
        self.assertIn("Certificate reference belongs to another customer", source)
        self.assertIn("Certificate asset ownership does not match", source)

    def test_webhook_update_is_after_existing_verified_idempotent_receipt(self):
        source = (ROOT / "webhook_server.py").read_text(encoding="utf-8")
        verify_index = source.index("verify_shopify_webhook_hmac")
        claim_index = source.index("claim_order_paid_webhook_receipt")
        background_index = source.index("background_tasks.add_task")
        self.assertLess(verify_index, claim_index)
        self.assertLess(claim_index, background_index)
        self.assertIn("collector_vault.process_framed_order_paid(payload)", source)


if __name__ == "__main__":
    unittest.main()
