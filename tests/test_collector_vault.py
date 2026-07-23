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
FRAME_PRODUCT_ID = "gid://shopify/Product/10332579103027"
FRAME_VARIANT_ID = "gid://shopify/ProductVariant/53700496261427"
FRAME_SKU = "SC-FCC-A4-BLK"


def _segment(value):
    raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _session_token(
    *,
    customer=CUSTOMER_A,
    expires_in=300,
    audience=CLIENT_ID,
    secret=SECRET,
):
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
        secret.encode("utf-8"),
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


def _frame_environment():
    return {
        "FRAMED_CERTIFICATE_PRODUCT_ID": FRAME_PRODUCT_ID,
        "FRAMED_CERTIFICATE_VARIANT_ID": FRAME_VARIANT_ID,
        "FRAMED_CERTIFICATE_PRODUCT_HANDLE": "framed-collector-certificate",
    }


def _frame_product_payload(*, status="ACTIVE", published=True, variant_available=True):
    return {
        "product": {
            "id": FRAME_PRODUCT_ID,
            "title": "Framed Collector Certificate",
            "handle": "framed-collector-certificate",
            "descriptionHtml": (
                "<p>Frame the proof.</p>"
                "<ul>"
                "<li>Premium black frame</li>"
                "<li>A4 landscape format</li>"
                "<li>Professionally printed and installed</li>"
                "<li>Ready to hang</li>"
                "</ul>"
            ),
            "status": status,
            "onlineStoreUrl": (
                "https://www.sportscaveshop.com/products/framed-collector-certificate"
                if published
                else None
            ),
            "tracksInventory": False,
            "featuredImage": {
                "url": "https://cdn.shopify.com/frame.jpg",
                "altText": "Framed Collector Certificate",
                "width": 1200,
                "height": 900,
            },
            "variants": {
                "nodes": [
                    {
                        "id": FRAME_VARIANT_ID,
                        "sku": FRAME_SKU,
                        "availableForSale": variant_available,
                        "inventoryItem": {"tracked": False},
                        "contextualPricing": {
                            "price": {
                                "amount": "99.0",
                                "currencyCode": "AUD",
                            }
                        },
                    }
                ]
            },
        }
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

    def test_shopify_shpss_app_secret_is_used_for_session_tokens(self):
        prefixed_secret = "shpss_collector-vault-test-secret"
        with (
            patch.dict(
                os.environ,
                {"SHOPIFY_CLIENT_SECRET": prefixed_secret},
                clear=True,
            ),
            patch.object(
                collector_vault.shopify_sync,
                "get_config",
                return_value={"store_domain": SHOP_DOMAIN},
            ),
        ):
            result = collector_vault.verify_shopify_session_token(
                _session_token(secret=prefixed_secret),
                audience=CLIENT_ID,
            )
        self.assertEqual(result["shopify_customer_id"], CUSTOMER_A)

    def test_shopify_admin_access_token_is_not_used_as_session_secret(self):
        with patch.dict(
            os.environ,
            {"SHOPIFY_CLIENT_SECRET": "shpat_not-a-shared-secret"},
            clear=True,
        ):
            self.assertEqual(collector_vault._session_token_secrets(), [])

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
                    "JUDGEME_PUBLIC_API_TOKEN": "public-test-token",
                    "JUDGEME_SHOP_DOMAIN": SHOP_DOMAIN,
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
                    "JUDGEME_PUBLIC_API_TOKEN": "public-test-token",
                    "JUDGEME_SHOP_DOMAIN": SHOP_DOMAIN,
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
                    "JUDGEME_PUBLIC_API_TOKEN": "public-test-token",
                    "JUDGEME_SHOP_DOMAIN": SHOP_DOMAIN,
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


class CollectorVaultReadinessTests(unittest.TestCase):
    def setUp(self):
        collector_vault._FRAME_PRODUCT_CACHE.clear()

    def test_dedicated_signing_secret_is_required(self):
        with patch.dict(
            os.environ,
            {
                "SHOPIFY_CLIENT_SECRET": "shopify-session-test-secret",
                "COLLECTOR_VAULT_ASSET_SIGNING_SECRET": "",
            },
            clear=True,
        ):
            with self.assertRaises(collector_vault.CollectorVaultUnavailableError):
                collector_vault._asset_signing_secret()

    def test_readiness_reports_configuration_states_without_values(self):
        configured = {
            **_frame_environment(),
            "SHOPIFY_CLIENT_ID": CLIENT_ID,
            "SHOPIFY_CLIENT_SECRET": "shpss_readiness-test-secret",
            "COLLECTOR_VAULT_ASSET_SIGNING_SECRET": SECRET,
            "JUDGEME_PRIVATE_API_TOKEN": "private-test-token",
            "JUDGEME_PUBLIC_API_TOKEN": "public-test-token",
            "JUDGEME_SHOP_DOMAIN": SHOP_DOMAIN,
        }
        with (
            patch.dict(os.environ, configured, clear=True),
            patch.object(
                collector_vault,
                "get_frame_product",
                return_value={
                    "state": "framed_product_draft",
                    "available": False,
                },
            ),
            patch.object(
                collector_vault.supabase_backend,
                "is_configured",
                return_value=True,
            ),
        ):
            readiness = collector_vault.collector_vault_readiness(
                check_shopify=True
            )
        self.assertEqual(readiness["judge_me_state"], "judge_me_configured")
        self.assertEqual(
            readiness["framed_product_state"],
            "framed_product_draft",
        )
        self.assertEqual(
            readiness["signing_state"],
            "signing_secret_configured",
        )
        self.assertEqual(
            readiness["session_auth_state"],
            "shopify_session_auth_configured",
        )
        self.assertEqual(
            readiness["database_state"],
            "collector_vault_database_configured",
        )
        self.assertEqual(
            readiness["backend_state"],
            "collector_vault_backend_ready",
        )
        self.assertNotIn("private-test-token", json.dumps(readiness))
        self.assertNotIn(SECRET, json.dumps(readiness))

    def test_readiness_reports_missing_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            readiness = collector_vault.collector_vault_readiness()
        self.assertEqual(readiness["judge_me_state"], "judge_me_not_configured")
        self.assertEqual(
            readiness["framed_product_state"],
            "framed_product_not_configured",
        )
        self.assertEqual(readiness["signing_state"], "signing_secret_missing")
        self.assertEqual(
            readiness["backend_state"],
            "collector_vault_backend_not_ready",
        )

    def test_frame_product_uses_configured_product_gid_and_verifies_variant(self):
        with (
            patch.dict(os.environ, _frame_environment(), clear=True),
            patch.object(
                collector_vault.shopify_sync,
                "graphql_request",
                return_value=(_frame_product_payload(), "2026-04"),
            ) as request,
        ):
            product = collector_vault.get_frame_product(force=True)
        query = request.call_args.args[0]
        variables = request.call_args.kwargs["variables"]
        self.assertIn("product(id: $id)", query)
        self.assertEqual(variables["id"], FRAME_PRODUCT_ID)
        self.assertEqual(product["product_id"], FRAME_PRODUCT_ID)
        self.assertEqual(product["variant_id"], FRAME_VARIANT_ID)
        self.assertEqual(product["sku"], FRAME_SKU)
        self.assertEqual(product["title"], "Framed Collector Certificate")
        self.assertEqual(
            product["image"]["url"],
            "https://cdn.shopify.com/frame.jpg",
        )
        self.assertEqual(
            product["inclusions"],
            [
                "Premium black frame",
                "A4 landscape format",
                "Professionally printed and installed",
            ],
        )
        self.assertEqual(product["state"], "ready_for_purchase")
        self.assertEqual(
            product["contextual_price"],
            {"amount": "99.0", "currency_code": "AUD"},
        )
        self.assertFalse(product["inventory_tracked"])

    def test_frame_product_identity_mismatch_is_never_substituted(self):
        payload = _frame_product_payload()
        payload["product"]["handle"] = "framed-collector-certificate-renamed"
        with (
            patch.dict(os.environ, _frame_environment(), clear=True),
            patch.object(
                collector_vault.shopify_sync,
                "graphql_request",
                return_value=(payload, "2026-04"),
            ),
        ):
            product = collector_vault.get_frame_product(force=True)
        self.assertEqual(product["product_id"], FRAME_PRODUCT_ID)
        self.assertEqual(product["state"], "framed_product_identity_mismatch")
        self.assertFalse(product["available"])
        self.assertEqual(
            product["handle"],
            "framed-collector-certificate-renamed",
        )

    def test_frame_product_accepts_numeric_config_and_normalizes_to_gids(self):
        environment = {
            "FRAMED_CERTIFICATE_PRODUCT_ID": FRAME_PRODUCT_ID.rsplit("/", 1)[-1],
            "FRAMED_CERTIFICATE_VARIANT_ID": FRAME_VARIANT_ID.rsplit("/", 1)[-1],
            "FRAMED_CERTIFICATE_PRODUCT_HANDLE": "framed-collector-certificate",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(
                collector_vault.shopify_sync,
                "graphql_request",
                return_value=(_frame_product_payload(), "2026-04"),
            ) as request,
        ):
            product = collector_vault.get_frame_product(force=True)
        self.assertEqual(
            request.call_args.kwargs["variables"]["id"],
            FRAME_PRODUCT_ID,
        )
        self.assertEqual(product["product_id"], FRAME_PRODUCT_ID)
        self.assertEqual(product["variant_id"], FRAME_VARIANT_ID)
        self.assertTrue(product["available"])

    def test_frame_product_variant_must_belong_to_configured_product(self):
        payload = _frame_product_payload()
        payload["product"]["variants"]["nodes"][0]["id"] = (
            "gid://shopify/ProductVariant/999"
        )
        with (
            patch.dict(os.environ, _frame_environment(), clear=True),
            patch.object(
                collector_vault.shopify_sync,
                "graphql_request",
                return_value=(payload, "2026-04"),
            ),
        ):
            product = collector_vault.get_frame_product(force=True)
        self.assertEqual(product["state"], "framed_product_identity_mismatch")
        self.assertFalse(product["available"])

    def test_frame_product_draft_unpublished_and_unavailable_states_are_hidden(self):
        scenarios = [
            (_frame_product_payload(status="DRAFT"), "framed_product_draft"),
            (
                _frame_product_payload(published=False),
                "framed_product_not_published",
            ),
            (
                {
                    **_frame_product_payload(),
                    "product": {
                        **_frame_product_payload()["product"],
                        "featuredImage": None,
                    },
                },
                "framed_product_image_missing",
            ),
            (
                _frame_product_payload(variant_available=False),
                "framed_variant_unavailable",
            ),
        ]
        for payload, expected_state in scenarios:
            with self.subTest(expected_state=expected_state):
                collector_vault._FRAME_PRODUCT_CACHE.clear()
                with (
                    patch.dict(os.environ, _frame_environment(), clear=True),
                    patch.object(
                        collector_vault.shopify_sync,
                        "graphql_request",
                        return_value=(payload, "2026-04"),
                    ),
                ):
                    product = collector_vault.get_frame_product(force=True)
                self.assertEqual(product["state"], expected_state)
                self.assertFalse(product["available"])

    def test_handle_lookup_is_discovery_fallback_not_purchase_identity(self):
        fallback_environment = {
            "FRAMED_CERTIFICATE_VARIANT_ID": FRAME_VARIANT_ID,
            "FRAMED_CERTIFICATE_PRODUCT_HANDLE": "framed-collector-certificate",
        }
        with (
            patch.dict(os.environ, fallback_environment, clear=True),
            patch.object(
                collector_vault.shopify_sync,
                "graphql_request",
            ) as request,
        ):
            product = collector_vault.get_frame_product(force=True)
        self.assertEqual(
            product["state"],
            "framed_product_not_configured",
        )
        self.assertFalse(product["available"])
        request.assert_not_called()


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
                    "JUDGEME_PUBLIC_API_TOKEN": "public-token",
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
        self.assertNotIn("public-token", json.dumps(captured["json"]))
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
        self.assertEqual(
            response.json()["error_code"],
            "customer_authentication_failed",
        )
        self.assertEqual(
            response.headers["x-sports-cave-error-code"],
            "customer_authentication_failed",
        )
        self.assertTrue(response.headers["x-sports-cave-request-id"])

    def test_collector_api_exposes_only_short_deployment_revision(self):
        revision = "12997c6fa76a1d25863816a77000c24e44e987b3"
        with patch.dict(
            os.environ,
            {"RENDER_GIT_COMMIT": revision},
            clear=False,
        ):
            response = TestClient(self.app).get(
                "/api/collector-vault/bootstrap"
            )
        self.assertEqual(
            response.headers["x-sports-cave-revision"],
            revision[:12],
        )
        self.assertNotIn(revision, response.text)

    def test_bootstrap_accepts_production_style_shopify_app_secret(self):
        prefixed_secret = "shpss_collector-vault-production-style-secret"
        payload = {
            "certificates": [
                {
                    "reference": "opaque",
                    "product_title": "The Mountain Chooses",
                }
            ],
            "review_prompt": None,
            "frame_product": {"available": False},
        }
        with (
            patch.dict(
                os.environ,
                {
                    "SHOPIFY_CLIENT_ID": CLIENT_ID,
                    "SHOPIFY_CLIENT_SECRET": prefixed_secret,
                },
                clear=True,
            ),
            patch.object(
                collector_vault.shopify_sync,
                "get_config",
                return_value={"store_domain": SHOP_DOMAIN},
            ),
            patch.object(
                collector_vault,
                "build_vault_payload",
                return_value=payload,
            ) as build_payload,
        ):
            response = TestClient(self.app).get(
                "/api/collector-vault/bootstrap",
                headers={
                    "Authorization": (
                        f"Bearer {_session_token(secret=prefixed_secret)}"
                    )
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["certificates"], payload["certificates"])
        self.assertTrue(response.headers["x-sports-cave-request-id"])
        build_payload.assert_called_once_with(CUSTOMER_A)

    def test_bootstrap_loads_collection_when_optional_frame_table_is_missing(self):
        class MissingFrameTableError(RuntimeError):
            sqlstate = "42P01"

        class Cursor:
            def __init__(self, *, rows=None, error=None):
                self.rows = list(rows or [])
                self.error = error
                self.query = ""

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, query, _params):
                self.query = str(query)
                if self.error:
                    raise self.error

            def fetchall(self):
                return list(self.rows)

        class Connection:
            def __init__(self, cursor):
                self._cursor = cursor

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return self._cursor

        base_cursor = Cursor(rows=[_certificate_row()])
        frame_cursor = Cursor(error=MissingFrameTableError("relation is missing"))
        connections = [
            Connection(base_cursor),
            Connection(frame_cursor),
        ]
        with (
            patch.dict(
                os.environ,
                {"COLLECTOR_VAULT_ASSET_SIGNING_SECRET": SECRET},
                clear=True,
            ),
            patch.object(
                collector_vault,
                "verify_shopify_session_token",
                return_value={"shopify_customer_id": CUSTOMER_A},
            ),
            patch.object(
                collector_vault.supabase_backend,
                "is_configured",
                return_value=True,
            ),
            patch.object(
                collector_vault.supabase_backend,
                "connect",
                side_effect=connections,
            ),
            patch.object(collector_vault, "get_frame_product") as frame_product,
        ):
            response = TestClient(self.app).get(
                "/api/collector-vault/bootstrap",
                headers={"Authorization": "Bearer signed-customer-token"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["certificates"]), 1)
        self.assertFalse(response.json()["frame_product"]["available"])
        self.assertNotIn("collector_frame_requests", base_cursor.query)
        self.assertIn("collector_frame_requests", frame_cursor.query)
        frame_product.assert_not_called()

    def test_bootstrap_reports_core_certificate_query_failure_as_recoverable(self):
        with (
            patch.object(
                collector_vault,
                "verify_shopify_session_token",
                return_value={"shopify_customer_id": CUSTOMER_A},
            ),
            patch.object(
                collector_vault,
                "_list_owned_certificates_with_capabilities",
                side_effect=collector_vault.CollectorVaultDataError(
                    "certificate query failed"
                ),
            ),
        ):
            response = TestClient(self.app).get(
                "/api/collector-vault/bootstrap",
                headers={"Authorization": "Bearer signed-customer-token"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertTrue(
            response.json()["error"].startswith(
                "Your collection could not be loaded. Please try again. Reference "
            )
        )
        self.assertEqual(
            response.json()["error_code"],
            "collection_data_unavailable",
        )
        self.assertEqual(
            response.headers["x-sports-cave-error-code"],
            "collection_data_unavailable",
        )
        self.assertNotIn("certificate query failed", response.text)

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


class CollectorVaultBootstrapResilienceTests(unittest.TestCase):
    def test_missing_review_table_hides_prompt_without_failing_collection(self):
        class MissingReviewTableError(RuntimeError):
            sqlstate = "42P01"

        row = _certificate_row()
        with (
            patch.dict(
                os.environ,
                {
                    "COLLECTOR_VAULT_ASSET_SIGNING_SECRET": SECRET,
                    "JUDGEME_PRIVATE_API_TOKEN": "private-test-token",
                    "JUDGEME_PUBLIC_API_TOKEN": "public-test-token",
                    "JUDGEME_SHOP_DOMAIN": SHOP_DOMAIN,
                },
                clear=True,
            ),
            patch.object(
                collector_vault,
                "delivery_statuses",
                return_value={"gid://shopify/Order/44": True},
            ) as delivery_statuses,
            patch.object(
                collector_vault,
                "_reviewed_keys",
                side_effect=MissingReviewTableError("relation is missing"),
            ),
        ):
            prompt = collector_vault.review_prompt([row], CUSTOMER_A)
        self.assertIsNone(prompt)
        delivery_statuses.assert_not_called()

    def test_missing_optional_preview_does_not_hide_certificate(self):
        row = _certificate_row()
        row["certificate_preview_image_url"] = ""
        with patch.dict(
            os.environ,
            {"COLLECTOR_VAULT_ASSET_SIGNING_SECRET": SECRET},
            clear=True,
        ):
            certificates = collector_vault._public_certificate_rows([row])
        self.assertEqual(len(certificates), 1)
        self.assertIsNone(certificates[0]["preview_url"])
        self.assertTrue(certificates[0]["pdf_url"])

    def test_missing_signing_secret_returns_metadata_and_disables_optional_features(self):
        row = _certificate_row()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                collector_vault,
                "_list_owned_certificates_with_capabilities",
                return_value=(
                    [row],
                    {"secure_assets": False, "frame_requests": False},
                ),
            ),
            patch.object(collector_vault, "review_prompt") as review_prompt,
            patch.object(collector_vault, "get_frame_product") as frame_product,
        ):
            payload = collector_vault.build_vault_payload(CUSTOMER_A)
        self.assertEqual(len(payload["certificates"]), 1)
        certificate = payload["certificates"][0]
        self.assertEqual(certificate["product_title"], "The Mountain Chooses")
        self.assertIsNone(certificate["preview_url"])
        self.assertIsNone(certificate["pdf_url"])
        self.assertIsNone(certificate["print_url"])
        self.assertTrue(certificate["reference"].startswith("metadata-"))
        self.assertIsNone(payload["review_prompt"])
        self.assertFalse(payload["frame_product"]["available"])
        review_prompt.assert_not_called()
        frame_product.assert_not_called()

    def test_one_malformed_certificate_does_not_fail_valid_collection(self):
        valid = _certificate_row()
        malformed = {**_certificate_row(), "certificate_row_id": "not-an-id"}
        with patch.dict(
            os.environ,
            {"COLLECTOR_VAULT_ASSET_SIGNING_SECRET": SECRET},
            clear=True,
        ):
            certificates = collector_vault._public_certificate_rows(
                [malformed, valid]
            )
        self.assertEqual(len(certificates), 1)
        self.assertEqual(certificates[0]["product_title"], "The Mountain Chooses")


class CollectorVaultImplementationTests(unittest.TestCase):
    def test_render_declares_frame_product_variables_without_values(self):
        source = (ROOT / "render.yaml").read_text(encoding="utf-8")
        for name in (
            "FRAMED_CERTIFICATE_PRODUCT_HANDLE",
            "FRAMED_CERTIFICATE_PRODUCT_ID",
            "FRAMED_CERTIFICATE_VARIANT_ID",
        ):
            self.assertEqual(source.count(f"key: {name}"), 2)
        self.assertGreaterEqual(source.count("sync: false"), 6)
        self.assertNotIn("gid://shopify/Product/", source)
        self.assertNotIn("gid://shopify/ProductVariant/", source)

    def test_bootstrap_exposes_only_verified_frame_product_presentation(self):
        frame_product = {
            "available": True,
            "product_id": FRAME_PRODUCT_ID,
            "handle": "framed-collector-certificate",
            "title": "Framed Collector Certificate",
            "image": {
                "url": "https://cdn.shopify.com/frame.jpg",
                "alt_text": "Framed Collector Certificate",
            },
            "inclusions": [
                "Premium black frame",
                "A4 landscape format",
                "Professionally printed and installed",
                "Ready to hang",
            ],
            "variant_id": FRAME_VARIANT_ID,
            "contextual_price": {
                "amount": "99.0",
                "currency_code": "AUD",
            },
        }
        with (
            patch.object(
                collector_vault,
                "_list_owned_certificates_with_capabilities",
                return_value=(
                    [_certificate_row()],
                    {"secure_assets": True, "frame_requests": True},
                ),
            ),
            patch.object(
                collector_vault,
                "get_frame_product",
                return_value=frame_product,
            ),
            patch.object(collector_vault, "review_prompt", return_value=None),
            patch.object(
                collector_vault,
                "_public_certificate_rows",
                return_value=[],
            ),
        ):
            payload = collector_vault.build_vault_payload(CUSTOMER_A)
        self.assertTrue(payload["frame_product"]["available"])
        self.assertEqual(
            payload["frame_product"]["title"],
            "Framed Collector Certificate",
        )
        self.assertEqual(
            payload["frame_product"]["image"]["url"],
            "https://cdn.shopify.com/frame.jpg",
        )
        self.assertEqual(len(payload["frame_product"]["inclusions"]), 3)
        self.assertEqual(
            payload["frame_product"]["variant_id"],
            FRAME_VARIANT_ID,
        )

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

    def test_framed_order_ignores_request_reference_on_wrong_variant(self):
        payload = {
            "id": 9001,
            "name": "#9001",
            "customer": {"id": 101},
            "line_items": [
                {
                    "variant_id": 999,
                    "properties": [
                        {
                            "name": "_sports_cave_frame_request",
                            "value": "fb09c2cf-1a8d-4bd9-9f50-c71d6300fd15",
                        }
                    ],
                }
            ],
        }
        with (
            patch.dict(os.environ, _frame_environment(), clear=True),
            patch.object(collector_vault.supabase_backend, "connect") as connect,
        ):
            result = collector_vault.process_framed_order_paid(payload)
        self.assertEqual(result, {"updated": 0})
        connect.assert_not_called()

    def test_migration_keeps_collector_tables_server_only(self):
        source = (ROOT / "migrations" / "20260723_collector_vault.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "REVOKE ALL ON collector_frame_requests FROM anon, authenticated",
            source,
        )
        self.assertIn(
            "REVOKE ALL ON collector_reviews FROM anon, authenticated",
            source,
        )

    def test_review_content_is_not_persisted_in_submission_state(self):
        source = (
            Path(collector_vault.__file__).read_text(encoding="utf-8")
        )
        reserve_source = source[
            source.index("def _reserve_review_submission"):
            source.index("def _upload_review_photo")
        ]
        self.assertIn("review_body=''", reserve_source)
        self.assertNotIn("body, existing.get", reserve_source)


if __name__ == "__main__":
    unittest.main()
