"""Reproducible local render timings; --baseline loads tracked HEAD code read-only."""
from pathlib import Path
import importlib.abc
import importlib.util
import json
import statistics
import subprocess
import sys
from timeit import repeat
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def baseline():
    names=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines()
    code={name[:-3].replace('/','.').replace('\\','.'):subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT).decode('utf-8')
          for name in names if name.endswith('.py')}
    class Head(importlib.abc.MetaPathFinder,importlib.abc.Loader):
        def find_spec(self,fullname,path=None,target=None):
            if fullname in code:return importlib.util.spec_from_loader(fullname,self)
        def create_module(self,spec):return None
        def exec_module(self,module):
            import linecache
            module.__file__=str(ROOT/(module.__name__.replace('.','/')+'.py'))
            linecache.cache[module.__file__]=(len(code[module.__name__]),None,code[module.__name__].splitlines(True),module.__file__)
            exec(compile(code[module.__name__],module.__file__,'exec'),module.__dict__)
    sys.meta_path.insert(0,Head())


if '--baseline' in sys.argv:baseline()
if '--test' in sys.argv or '--suite' in sys.argv:
    import unittest
    tests=Path(sys.argv[sys.argv.index('--suite')+1]).read_text().splitlines() if '--suite' in sys.argv else [sys.argv[sys.argv.index('--test')+1]]
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(tests))
    sys.exit(not result.wasSuccessful())

from tests.test_crm_abandoned_checkout import native_document,checkout
from tests.test_crm_send_flow import CFG
from crm_abandoned_checkout import context,hydrate
from crm_campaign_content import render_campaign
from unittest.mock import patch


def timing(fn):
    fn()
    return round(statistics.median(repeat(fn,number=100,repeat=5))*10,3)


with patch('requests.sessions.Session.request',side_effect=AssertionError('No external I/O')):
    data=context(checkout(items=2),edition_reader=lambda **_:[]);doc=native_document()
    results={'mode':'HEAD' if '--baseline' in sys.argv else 'working_tree',
             'legacy_hydrate_and_render_ms':timing(lambda:render_campaign(hydrate(doc,data),CFG))}
    if '--baseline' not in sys.argv:
        from crm_checkout_elements import starter,element
        from crm_middle_sections import commit_middle
        from crm_automation_preview_cache import output
        from unittest.mock import Mock
        visual=native_document();commit_middle(visual,starter());visual['content_mode']='HTML'
        results['composable_hydrate_and_render_ms']=timing(lambda:render_campaign(hydrate(visual,data),CFG))
        commit_middle(visual,[element('headline',text='Return to your collection'),element()])
        results['minimal_hydrate_and_render_ms']=timing(lambda:render_campaign(hydrate(visual,data),CFG))
        state={};store=Mock();store.preview_document.return_value=(hydrate(visual,data),'Fixture')
        from crm_campaign_sections import section_defaults
        cfg={**CFG,'email_defaults':section_defaults(CFG)}
        results['cached_preview_output_ms']=timing(lambda:output(state,store,visual,cfg))
    print(json.dumps(results))
