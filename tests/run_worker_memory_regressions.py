"""Run delivery regressions against an explicitly started loopback SQL fixture."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
assert os.environ.get('CRM_FIXTURE_SQL_PORT') == '8898', 'Dedicated local fixture on 8898 required'
os.environ['CRM_TEST_POSTGRES'] = '1'
MODULES = (
    'test_crm_automation_publication', 'test_crm_native_automations',
    'test_crm_checkout_reliability', 'test_crm_batch_dispatch',
    'test_crm_campaign_preparation', 'test_crm_flow_v5',
    'test_crm_automation_timing', 'test_crm_thumbnail_store',
)
# Real thumbnails are tested separately with network-disabled containers.
# Publication regressions should not install browsers or start asynchronous I/O.
with patch('crm_thumbnail_cache.prewarm'), patch('requests.sessions.Session.request', side_effect=AssertionError('External I/O forbidden')):
    suite = unittest.defaultTestLoader.loadTestsFromNames(['tests.'+name for name in MODULES])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
raise SystemExit(not result.wasSuccessful())
