import sys
import unittest
from unittest.mock import patch

import certificate_job


class CertificateJobTimeoutTests(unittest.TestCase):
    def test_worker_timeout_reports_last_stage(self):
        command = [
            sys.executable,
            "-u",
            "-c",
            (
                "import json, time; "
                "print(json.dumps({'event':'certificate_stage','stage':'PDF_generation','status':'started'}), flush=True); "
                "time.sleep(5)"
            ),
        ]

        result = certificate_job._run_worker_command(
            command,
            timeout_seconds=0.2,
            source_page="Orders",
            row={"order": "#SC2851", "edition_order_id": "edition-1"},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["last_stage"], "PDF_generation")
        self.assertIn("certificate job timed out at PDF_generation", result["error"])

    def test_public_certificate_record_redacts_customer_data(self):
        record = certificate_job._public_certificate_record(
            {
                "certificate_id": "SC-TEST",
                "pdf_url": "https://cdn.example/test.pdf",
                "customer_email": "private@example.com",
                "customer_name": "Private Customer",
            }
        )

        self.assertEqual(record["certificate_id"], "SC-TEST")
        self.assertNotIn("customer_email", record)
        self.assertNotIn("customer_name", record)

    def test_upload_worker_uses_no_schema_certificate_backend_calls(self):
        row = {
            "order": "#SC2851",
            "shopify_order_id": "gid://shopify/Order/1",
            "shopify_line_item_id": "gid://shopify/LineItem/1",
            "edition_order_id": "edition-1",
            "edition_number": 1,
            "edition_total": 100,
            "product_title": "Test Product",
            "product_handle": "test-product",
        }
        base_record = {
            "order_gid": "gid://shopify/Order/1",
            "shopify_order_id": "gid://shopify/Order/1",
            "line_item_id": "gid://shopify/LineItem/1",
            "edition_number": 1,
            "edition_total": 100,
            "line_item_unit_index": 1,
            "local_pdf_path": "",
        }
        generated_record = {**base_record, "local_pdf_path": "certificate.pdf"}
        uploaded_record = {
            **generated_record,
            "certificate_id": "SC-SC2851-001",
            "certificate_pdf_url": "https://cdn.example/certificate.pdf",
            "status": "Ready",
        }

        with (
            patch("shopify_sync.get_config", return_value={"configured": True}),
            patch("certificate_job._existing_uploaded_certificate", return_value={}),
            patch("supabase_backend.generate_certificate_for_edition_order", return_value="") as generate_backend,
            patch("certificate_engine.certificate_record_from_order_row", return_value=base_record),
            patch("certificate_engine.generate_local_certificate_for_record", return_value=generated_record),
            patch("certificate_engine.upload_generated_certificate_record", return_value=uploaded_record),
            patch(
                "certificate_engine.save_certificate_record_to_order",
                return_value={
                    "saved": True,
                    "metafields_synced": True,
                    "record": uploaded_record,
                },
            ) as save_record,
        ):
            result = certificate_job.run_certificate_job(row, source_page="Orders", upload=True)

        self.assertTrue(result["ok"])
        self.assertFalse(generate_backend.call_args.kwargs["ensure_schema_first"])
        self.assertFalse(save_record.call_args.kwargs["ensure_schema_first"])

    def test_missing_edition_record_fails_before_backend_schema_work(self):
        with patch("supabase_backend.ensure_schema", side_effect=AssertionError("ensure_schema was called")):
            with self.assertRaises(ValueError):
                certificate_job.run_certificate_job(
                    {
                        "order": "#SC2851",
                        "shopify_order_id": "gid://shopify/Order/1",
                        "edition_number": 1,
                    },
                    source_page="Orders",
                    upload=False,
                )


if __name__ == "__main__":
    unittest.main()
