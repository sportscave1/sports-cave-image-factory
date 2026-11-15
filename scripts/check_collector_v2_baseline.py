"""Read-only in-memory V1 comparison for the unrelated campaign review failure."""
from pathlib import Path
import subprocess,sys,types,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
for name in ('crm_shopify','crm_collector_images','crm_collector_templates','crm_collector_resolver','crm_campaign_library'):
    path=ROOT/'tmp/collector-v2-baseline'/(name+'.py')
    source=(subprocess.check_output(['git','show','HEAD:crm_shopify.py'],cwd=ROOT).decode()
            if name=='crm_shopify' else path.read_text(encoding='utf-8'))
    module=types.ModuleType(name);module.__file__=str(ROOT/(name+'.py'));sys.modules[name]=module
    exec(compile(source,module.__file__,'exec'),module.__dict__)
suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_crm_send_flow.SendFlowUiTests.test_first_send_now_is_review_only_and_shows_off')
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
