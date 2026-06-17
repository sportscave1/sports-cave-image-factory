import unittest

import supabase_backend


class LimitedEditionPhase2Tests(unittest.TestCase):
    def test_csv_import_values_use_latest_sent_for_next_number(self):
        row = {
            "Shopify Handle": "Jason-Richards-Art",
            "Product Title": "Jason Richards Wall Art",
            "Edition Name": "2026 Edition",
            "Latest Sent": "69",
            "Total Editions": "100",
            "Status": "Active",
        }

        parsed = supabase_backend._limited_edition_import_values(row)

        self.assertEqual(parsed["shopify_handle"], "jason-richards-art")
        self.assertEqual(parsed["edition_name"], "2026 Edition")
        self.assertEqual(parsed["latest_sent"], 69)
        self.assertEqual(parsed["next_edition_number"], 70)
        self.assertEqual(parsed["edition_total"], 100)
        self.assertEqual(parsed["status"], "active")

    def test_csv_import_values_read_edition_number_total_pair(self):
        parsed = supabase_backend._limited_edition_import_values(
            {
                "Shopify Handle": "legends-kobe-jordan",
                "Edition No.": "#29/100",
            }
        )

        self.assertEqual(parsed["latest_sent"], 29)
        self.assertEqual(parsed["next_edition_number"], 30)
        self.assertEqual(parsed["edition_total"], 100)

    def test_active_run_normalization_overrides_legacy_counter(self):
        row = {
            "shopify_handle": "jalen-brunson",
            "product_title": "Jalen Brunson Built for Big Moments",
            "edition_total": 100,
            "next_edition_number": 12,
            "run_edition_name": "Playoff Edition",
            "run_edition_total": 150,
            "run_next_edition_number": 71,
            "run_status": "active",
            "active_run_max_assigned": 70,
        }

        normalized = supabase_backend._normalize_edition_product_row(row)

        self.assertEqual(normalized["edition_name"], "Playoff Edition")
        self.assertEqual(normalized["edition_total"], 150)
        self.assertEqual(normalized["next_edition_number"], 71)
        self.assertEqual(normalized["latest_sent"], 70)
        self.assertEqual(normalized["remaining_editions"], 80)
        self.assertTrue(normalized["active"])
        self.assertFalse(normalized["sold_out"])


if __name__ == "__main__":
    unittest.main()
