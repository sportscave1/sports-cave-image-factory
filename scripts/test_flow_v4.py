"""Local-only regression runner. Disposable SQL opt-in, no external providers."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
modules=['test_crm_flow_v4','test_crm_thumbnail_cache','test_crm_thumbnail_store','test_crm_flow_page','test_crm_flow_compact',
         'test_crm_flow_settings_removed','test_crm_native_automations','test_crm_automation_publication',
         'test_crm_discounts','test_crm_discount_delivery','test_crm_discount_editor_v2','test_crm_flow_builder']
modules=[m for m in modules if Path('tests',m+'.py').exists()]
# Publication prewarm is optional, tested separately with real bounded renders.
# It must not outlive tests that patch the provider/publication boundaries.
with patch('crm_thumbnail_cache.prewarm'):
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(['tests.'+m for m in modules]))
sys.exit(not result.wasSuccessful())
