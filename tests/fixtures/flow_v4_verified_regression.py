"""Strict local release gate: no skipped or waived sending invariants."""
from unittest import TestSuite
from unittest.mock import patch
from scripts.run_email_reliability import MODULES

class Gate(TestSuite):
    def run(self,result,debug=False):
        with patch('crm_thumbnail_cache.prewarm'):
            return super().run(result,debug)

def load_tests(loader,tests,pattern):
    extra=('flow_v4','thumbnail_cache','thumbnail_store','flow_page','flow_compact',
           'flow_settings_removed','automation_publication','discounts','discount_delivery',
           'discount_editor_v2','flow_builder')
    return Gate(loader.loadTestsFromNames(['tests.test_crm_'+m for m in dict.fromkeys((*MODULES,*extra))]+['tests.test_sports_cave_worker']))
