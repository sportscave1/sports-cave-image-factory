from decimal import Decimal
import inspect
import unittest

import seo_metrics
import seo_page


class SEOMetricContractTests(unittest.TestCase):
    def test_country_codes_and_query_rows_are_canonical(self):
        self.assertEqual(seo_metrics.normalize_gsc_country("AUS"), "AU")
        self.assertEqual(seo_metrics.normalize_gsc_country("USA"), "US")
        self.assertEqual(seo_metrics.normalize_gsc_country("GBR"), "UK")
        self.assertEqual(seo_metrics.normalize_gsc_country("CAN"), "CA")
        self.assertEqual(seo_metrics.normalize_gsc_country("NZL"), "NZ")
        rows = seo_metrics.aggregate_query_rows(
            [
                {"query": "Sports   Cave", "country": "AUS", "device": "MOBILE", "clicks": 2, "impressions": 20, "average_position": 2},
                {"query": "sports cave", "country": "USA", "device": "DESKTOP", "clicks": 3, "impressions": 30, "average_position": 8},
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["normalized_query"], "sports cave")
        self.assertEqual(rows[0]["clicks"], Decimal("5"))
        self.assertEqual(rows[0]["ctr"], Decimal("0.1"))
        self.assertEqual(rows[0]["average_position"], Decimal("5.6"))
        self.assertEqual(rows[0]["market_mix"], ["AU", "US"])

    def test_filters_apply_before_grouping(self):
        rows = [
            {"query": "sports cave", "country": "AUS", "device": "MOBILE", "clicks": 2, "impressions": 20, "average_position": 2},
            {"query": "sports cave", "country": "USA", "device": "DESKTOP", "clicks": 9, "impressions": 90, "average_position": 20},
        ]
        selected = seo_metrics.aggregate_query_rows(rows, market="AU", device="mobile")
        self.assertEqual(selected[0]["clicks"], Decimal("2"))
        self.assertEqual(selected[0]["average_position"], Decimal("2"))

    def test_rank_quality_is_impression_weighted_and_bounded(self):
        result = seo_metrics.rank_quality(
            [
                {"impressions": 100, "average_position": 2},
                {"impressions": 100, "average_position": 8},
                {"impressions": 100, "average_position": 15},
                {"impressions": 100, "average_position": 30},
                {"impressions": 100, "average_position": 60},
            ]
        )
        self.assertEqual(result["score"], Decimal("45.00"))
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)

    def test_opportunity_score_uses_observed_inputs_only(self):
        result = seo_metrics.opportunity_score(
            {"impressions": 500, "ctr": 0.01, "average_position": 9, "click_change": 3, "content_gap": True}
        )
        self.assertGreater(result["score"], 0)
        self.assertNotIn("search volume", result["explanation"].casefold())

    def test_overview_builds_only_the_selected_detail_table(self):
        source = inspect.getsource(seo_page._render_search_overview)
        self.assertIn("st.segmented_control", source)
        self.assertNotIn("st.tabs", source)
        self.assertEqual(source.count("_table("), 1)


if __name__ == "__main__":
    unittest.main()
