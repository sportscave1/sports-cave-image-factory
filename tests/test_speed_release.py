"""Bridge the scoped pytest contracts into the existing offline release gate."""
import unittest


class SpeedReleaseChecks(unittest.TestCase):
    def test_scoped_contracts(self):
        import pytest
        result = pytest.main(['-q', 'tests/test_speed_optimisation.py',
                              'tests/test_speed_companion.py',
                              'tests/test_speed_preview.py',
                              'tests/test_meta_review_speed.py',
                              'tests/test_meta_review_v3.py',
                              'tests/test_meta_review_live.py',
                              'tests/test_meta_review_country.py',
                              'tests/test_meta_review_reporting_window.py',
                              'tests/test_meta_review_active_cpc.py',
                              'tests/test_meta_review_tables.py',
                              'tests/test_meta_review_search.py',
                              'tests/test_worker_health_navigation.py',
                              'tests/test_task_recorder_navigation.py',
                              'tests/test_sidebar_navigation_cleanup.py',
                              'tests/test_marketplace.py',
                              'tests/test_marketplace_photo_cache.py',
                              'tests/test_database_read_pool.py',
                              'tests/test_marketplace_dropbox.py',
                              'tests/test_marketplace_accounts.py',
                              'tests/test_marketplace_media.py',
                              'tests/test_marketplace_notifications.py',
                              'tests/test_marketplace_collation.py'])
        self.assertEqual(int(result), 0)
