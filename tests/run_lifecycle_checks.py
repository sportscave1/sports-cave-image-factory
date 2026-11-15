"""Isolated test runner; optional thumbnail subprocesses are tested separately."""
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if '--baseline' in sys.argv:
    from tests.lifecycle_baseline import install
    install()
from unittest.mock import patch
names=['tests.test_crm_abandoned_checkout','tests.test_crm_automation_timing','tests.test_crm_flow_v4',
       'tests.test_crm_flow_v5','tests.test_crm_native_automations','tests.test_crm_shopify_automation_triggers',
       'tests.test_crm_automation_publication','tests.test_crm_automation_live']
if '--baseline' not in sys.argv:names.insert(0,'tests.test_crm_lifecycle_expansion')
with patch('crm_thumbnail_cache.prewarm'):
    suite=unittest.defaultTestLoader.loadTestsFromNames(names)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(not result.wasSuccessful())
