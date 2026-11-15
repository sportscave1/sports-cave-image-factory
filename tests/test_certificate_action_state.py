from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CertificateActionStateSourceTests(unittest.TestCase):
    def test_orders_certificate_action_has_stale_recovery_and_finally_cleanup(self):
        source = (ROOT / "orders_page.py").read_text(encoding="utf-8")

        self.assertIn("CERTIFICATE_ACTION_STALE_SECONDS = 300", source)
        self.assertIn("_clear_stale_certificate_action_state(source=\"Orders\")", source)
        self.assertIn("finally:\n        _clear_certificate_action_state(source=\"Orders\")", source)
        self.assertIn("run_certificate_job_with_timeout(row, source_page=\"Orders\", upload=True)", source)

    def test_prodigi_certificate_action_has_stale_recovery_and_finally_cleanup(self):
        source = (ROOT / "os_pages.py").read_text(encoding="utf-8")

        self.assertIn("PRODIGI_CERTIFICATE_ACTION_STALE_SECONDS = 300", source)
        self.assertIn("_prodigi_clear_stale_certificate_action_state()", source)
        self.assertIn("finally:\n                _prodigi_clear_certificate_action_state()", source)
        self.assertIn("run_certificate_job_with_timeout(row, source_page=\"Prodigi\", upload=True)", source)


if __name__ == "__main__":
    unittest.main()
