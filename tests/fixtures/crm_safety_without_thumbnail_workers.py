"""Run email safety independently of optional asynchronous thumbnail rendering.

Thumbnail prewarming writes no delivery state, but its background SQL otherwise
pollutes request-worker statement counters and concurrency timing benchmarks.
"""
import unittest
from unittest.mock import patch
from scripts.run_email_reliability import MODULES


class SafetySuite(unittest.TestSuite):
    def run(self,result,debug=False):
        with patch('crm_thumbnail_cache.prewarm'):
            return super().run(result,debug)


def load_tests(loader,tests,pattern):
    return SafetySuite(loader.loadTestsFromNames(
        ['tests.test_crm_'+name for name in MODULES]+['tests.test_sports_cave_worker']))
