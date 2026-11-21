"""Bridge the scoped pytest contracts into the existing offline release gate."""
import unittest


class SpeedReleaseChecks(unittest.TestCase):
    def test_scoped_contracts(self):
        import pytest
        result = pytest.main(['-q', 'tests/test_speed_optimisation.py',
                              'tests/test_speed_companion.py',
                              'tests/test_speed_preview.py',
                              'tests/test_worker_health_navigation.py',
                              'tests/test_task_recorder_navigation.py',
                              'tests/test_sidebar_navigation_cleanup.py',
                              'tests/test_marketplace.py'])
        self.assertEqual(int(result), 0)
