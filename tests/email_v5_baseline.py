"""Opt-in V5 baseline comparison, run through the disposable SQL runner.

Load the five pre-V5 application modules and three corresponding old tests in
memory. No checkout changes. New V5 tests are excluded from the old baseline.
"""
import subprocess
import sys
import types
import unittest
from pathlib import Path

REF='7f1481e1f7e54eb3665e3d0b9df789531e15eb5b'

def load_tests(loader,tests,pattern):
    sources={}
    names=('crm_email_size','crm_email_size_ui','crm_campaign_controls',
           'crm_campaign_send_ui','crm_campaign_page','test_crm_audience_prepare',
           'test_crm_email_size','test_crm_send_flow','test_crm_segment_performance',
           'test_crm_test_issue_groups')
    for name in names:
        path=('tests/' if name.startswith('test_') else '')+name+'.py'
        source=subprocess.check_output(['git','show',REF+':'+path],text=True,encoding='utf-8')
        sources[Path(path).resolve()]=source
        module=types.ModuleType(name);module.__file__=str(Path(path).resolve());sys.modules[name]=module
        exec(compile(source,module.__file__,'exec'),module.__dict__)
    # Source-contract tests must inspect the same source as the loaded baseline,
    # not the working-tree V5 implementation. This is process-local and read-only.
    read_text=Path.read_text
    def baseline_text(path,*args,**kwargs):
        source=sources.get(path.resolve())
        return source if source is not None else read_text(path,*args,**kwargs)
    Path.read_text=baseline_text
    suite=loader.discover('tests',pattern='test_crm_*.py')
    def keep(group):
        for item in group:
            if isinstance(item,unittest.TestSuite):yield from keep(item)
            elif not item.id().startswith('test_crm_email_v5.'):yield item
    return unittest.TestSuite(keep(suite))
