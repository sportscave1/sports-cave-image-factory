import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()
