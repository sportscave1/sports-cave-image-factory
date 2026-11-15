import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import certificate_engine
import certificate_service
import shopify_sync


class CertificateEngineTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "store_domain": "sports-cave.myshopify.com",
            "access_token": "test-token",
            "client_id": "",
            "client_secret": "",
            "api_version": "2026-04",
            "max_products": 25,
            "auth_mode": "Admin access token mode",
            "configured": True,
        }
        self.line_id = "gid://shopify/LineItem/555"
        self.order_payload = {
            "id": 1234,
            "name": "#SC1234",
            "financial_status": "paid",
            "processedAt": "2026-06-22T10:00:00Z",
            "customer": {"first_name": "Greg", "last_name": "Collector", "email": "greg@example.com"},
            "line_items": [
                {
                    "id": 555,
                    "product_id": 777,
                    "variant_id": 888,
                    "title": "Greg Murphy Lap of the Gods Wall Art",
                    "variant_title": "Black / XL",
                    "quantity": 1,
                    "handle": "greg-murphy-lap-of-the-gods-wall-art",
                }
            ],
        }

    def _allocation_metafield(self, numbers):
        return {
            "namespace": "sports_cave",
            "key": "edition_allocations",
            "type": "json",
            "value": json.dumps(
                {
                    "line_items": {
                        self.line_id: {
                            "line_item_id": self.line_id,
                            "product_id": "gid://shopify/Product/777",
                            "variant_id": "gid://shopify/ProductVariant/888",
                            "handle": "greg-murphy-lap-of-the-gods-wall-art",
                            "product_title": "Greg Murphy Lap of the Gods Wall Art",
                            "variant_title": "Black / XL",
                            "quantity": len(numbers),
                            "edition_numbers": numbers,
                            "edition_total": 100,
                        }
                    }
                }
            ),
        }

    def _certificate_metafield(self, certificates=None):
        return {
            "namespace": "sports_cave",
            "key": "certificates",
            "type": "json",
            "value": json.dumps(certificates or []),
            "compareDigest": "digest-1",
        }

    def _fake_fetch(self, metafields):
        return lambda owner_id, namespace="sports_cave", config=None, request_post=None: {
            "metafields": metafields,
            "api_version": "2026-04",
        }

    def _fake_pdf(self, output_dir, **kwargs):
        path = Path(output_dir) / (kwargs.get("filename") or "certificate.pdf")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return str(path)

    def test_existing_template_paths_are_detected(self):
        status = certificate_service.certificate_template_status()

        self.assertTrue(status["print_template_found"])
        self.assertTrue(status["preview_template_found"])
        self.assertTrue(Path(status["print_template_path"]).exists())
        self.assertTrue(Path(status["preview_template_path"]).exists())

    def test_one_allocation_creates_one_pdf_certificate_record(self):
        synced = []

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            shopify_sync,
            "fetch_metafields",
            side_effect=self._fake_fetch([self._allocation_metafield([96]), self._certificate_metafield()]),
        ), patch.object(
            certificate_service,
            "generate_certificate_pdf",
            side_effect=self._fake_pdf,
        ), patch.object(
            shopify_sync,
            "upload_pdf_to_shopify_files",
            return_value={"file_id": "gid://shopify/GenericFile/1", "url": "https://cdn.example/cert.pdf"},
        ), patch.object(
            shopify_sync,
            "sync_order_certificate_metafields",
            side_effect=lambda order_gid, certificates, compare_digest=None, config=None, request_post=None: synced.append(certificates),
        ):
            result = certificate_engine.generate_missing_certificates_for_order(
                self.order_payload,
                config=self.config,
                output_dir=tmpdir,
            )

        self.assertEqual(result["generated"], 1)
        self.assertEqual(len(synced[0]), 1)
        record = synced[0][0]
        self.assertEqual(record["edition_number"], 96)
        self.assertEqual(record["edition_display"], "#096/100")
        self.assertEqual(record["shopify_customer_id"], "")
        self.assertEqual(record["shopify_order_name"], "#SC1234")
        self.assertEqual(record["shopify_line_item_id"], self.line_id)
        self.assertEqual(record["shopify_product_id"], "gid://shopify/Product/777")
        self.assertEqual(record["shopify_variant_id"], "gid://shopify/ProductVariant/888")
        self.assertEqual(record["pdf_shopify_file_id"], "gid://shopify/GenericFile/1")
        self.assertEqual(record["pdf_size_bytes"], len(b"%PDF-1.4\n%%EOF\n"))
        self.assertNotIn("local_pdf_path", record)
        self.assertNotIn("preview_path", record)
        self.assertEqual(record["status"], "Ready")
        self.assertIn("SC-SC1234-GREG-MURPHY-LAP-OF-THE-GODS-WALL-ART-EDITION-096", record["certificate_id"])

    def test_quantity_two_creates_two_certificate_records(self):
        synced = []

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            shopify_sync,
            "fetch_metafields",
            side_effect=self._fake_fetch([self._allocation_metafield([96, 97]), self._certificate_metafield()]),
        ), patch.object(
            certificate_service,
            "generate_certificate_pdf",
            side_effect=self._fake_pdf,
        ), patch.object(
            shopify_sync,
            "upload_pdf_to_shopify_files",
            side_effect=[
                {"file_id": "gid://shopify/GenericFile/96", "url": "https://cdn.example/96.pdf"},
                {"file_id": "gid://shopify/GenericFile/97", "url": "https://cdn.example/97.pdf"},
            ],
        ), patch.object(
            shopify_sync,
            "sync_order_certificate_metafields",
            side_effect=lambda order_gid, certificates, compare_digest=None, config=None, request_post=None: synced.append(certificates),
        ):
            result = certificate_engine.generate_missing_certificates_for_order(
                self.order_payload,
                config=self.config,
                output_dir=tmpdir,
            )

        self.assertEqual(result["generated"], 2)
        self.assertEqual([record["edition_display"] for record in synced[0]], ["#096/100", "#097/100"])
        self.assertEqual([record["line_item_unit_index"] for record in synced[0]], [1, 2])

    def test_certificate_metafield_push_failure_does_not_lose_generated_certificate(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            shopify_sync,
            "fetch_metafields",
            side_effect=self._fake_fetch([self._allocation_metafield([96]), self._certificate_metafield()]),
        ), patch.object(
            certificate_service,
            "generate_certificate_pdf",
            side_effect=self._fake_pdf,
        ), patch.object(
            shopify_sync,
            "upload_pdf_to_shopify_files",
            return_value={"file_id": "gid://shopify/GenericFile/1", "url": "https://cdn.example/cert.pdf"},
        ), patch.object(
            shopify_sync,
            "sync_order_certificate_metafields",
            side_effect=shopify_sync.ShopifyAPIError("metafield failed"),
        ):
            result = certificate_engine.generate_missing_certificates_for_order(
                self.order_payload,
                config=self.config,
                output_dir=tmpdir,
            )

        self.assertEqual(result["generated"], 1)
        self.assertEqual(len(result["certificates"]), 1)
        self.assertEqual(result["certificates"][0]["pdf_url"], "https://cdn.example/cert.pdf")
        self.assertEqual(result["metafield_errors"], ["metafield failed"])

    def test_existing_certificate_metadata_prevents_duplicate_generation(self):
        existing = {
            "line_item_id": self.line_id,
            "line_item_unit_index": 1,
            "edition_number": 96,
            "edition_display": "#096",
            "pdf_url": "https://cdn.example/existing.pdf",
            "status": "Ready",
        }

        with patch.object(
            shopify_sync,
            "fetch_metafields",
            side_effect=self._fake_fetch([self._allocation_metafield([96]), self._certificate_metafield([existing])]),
        ), patch.object(certificate_service, "generate_certificate_pdf") as generate_pdf, patch.object(
            shopify_sync,
            "upload_pdf_to_shopify_files",
        ) as upload_pdf, patch.object(shopify_sync, "sync_order_certificate_metafields") as sync_certificates:
            result = certificate_engine.generate_missing_certificates_for_order(self.order_payload, config=self.config)

        self.assertEqual(result["generated"], 0)
        self.assertEqual(result["skipped"], 1)
        generate_pdf.assert_not_called()
        upload_pdf.assert_not_called()
        sync_certificates.assert_not_called()

    def test_missing_allocation_returns_waiting_for_edition_allocation(self):
        with patch.object(
            shopify_sync,
            "fetch_metafields",
            side_effect=self._fake_fetch([self._certificate_metafield()]),
        ), patch.object(shopify_sync, "sync_order_certificate_metafields") as sync_certificates:
            result = certificate_engine.generate_missing_certificates_for_order(self.order_payload, config=self.config)

        self.assertFalse(result["processed"])
        self.assertEqual(result["status"], "Waiting for edition allocation")
        sync_certificates.assert_not_called()

    def test_missing_template_returns_template_missing_instead_of_crashing(self):
        synced = []

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            certificate_service,
            "CERTIFICATE_TEMPLATE_PRINT_PATH",
            Path(tmpdir) / "missing-template.png",
        ), patch.object(
            shopify_sync,
            "fetch_metafields",
            side_effect=self._fake_fetch([self._allocation_metafield([96]), self._certificate_metafield()]),
        ), patch.object(
            shopify_sync,
            "sync_order_certificate_metafields",
            side_effect=lambda order_gid, certificates, compare_digest=None, config=None, request_post=None: synced.append(certificates),
        ):
            result = certificate_engine.generate_missing_certificates_for_order(
                self.order_payload,
                config=self.config,
                output_dir=tmpdir,
            )

        self.assertEqual(result["generated"], 0)
        self.assertEqual(synced[0][0]["status"], "Template missing")
        self.assertIn("Certificate template missing", synced[0][0]["sync_error"])

    def test_upload_failure_leaves_allocation_untouched_and_marks_upload_error(self):
        synced = []

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            shopify_sync,
            "fetch_metafields",
            side_effect=self._fake_fetch([self._allocation_metafield([96]), self._certificate_metafield()]),
        ), patch.object(
            certificate_service,
            "generate_certificate_pdf",
            side_effect=self._fake_pdf,
        ), patch.object(
            shopify_sync,
            "upload_pdf_to_shopify_files",
            side_effect=shopify_sync.ShopifyAPIError("Upload failed"),
        ), patch.object(
            shopify_sync,
            "sync_order_certificate_metafields",
            side_effect=lambda order_gid, certificates, compare_digest=None, config=None, request_post=None: synced.append(certificates),
        ), patch.object(shopify_sync, "sync_order_allocation_metafield") as sync_allocations:
            result = certificate_engine.generate_missing_certificates_for_order(
                self.order_payload,
                config=self.config,
                output_dir=tmpdir,
            )

        self.assertEqual(result["generated"], 0)
        self.assertEqual(synced[0][0]["status"], "Upload error")
        self.assertIn("Upload failed", synced[0][0]["sync_error"])
        sync_allocations.assert_not_called()

    def test_order_row_upload_rejects_empty_or_non_pdf_local_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = Path(tmpdir) / "certificate.pdf"
            bad_path.write_text("not a pdf", encoding="utf-8")
            record = {
                "order_name": "#SC1234",
                "handle": "greg-murphy-lap-of-the-gods-wall-art",
                "edition_number": 96,
                "edition_total": 100,
                "local_pdf_path": str(bad_path),
            }

            with self.assertRaises(shopify_sync.ShopifyAPIError):
                certificate_engine.upload_generated_certificate_record(record, config=self.config)

    def test_certificate_metafield_record_removes_local_only_paths(self):
        record = certificate_engine.certificate_metafield_record(
            {
                "certificate_id": "SC-SC1234-096",
                "pdf_url": "https://cdn.example/certificate.pdf",
                "local_pdf_path": "C:/local/certificate.pdf",
                "preview_path": "C:/local/certificate.png",
                "local_print_jpg_path": "C:/local/certificate-print.jpg",
                "local_preview_image_path": "C:/local/certificate-preview.webp",
                "pdf_size_bytes": 123,
            }
        )

        self.assertEqual(record["pdf_url"], "https://cdn.example/certificate.pdf")
        self.assertEqual(record["pdf_size_bytes"], 123)
        self.assertNotIn("local_pdf_path", record)
        self.assertNotIn("preview_path", record)
        self.assertNotIn("local_print_jpg_path", record)
        self.assertNotIn("local_preview_image_path", record)


if __name__ == "__main__":
    unittest.main()
