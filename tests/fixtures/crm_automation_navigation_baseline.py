"""Reproduce the pre-navigation-fix editor, without modifying the checkout."""
from pathlib import Path
import subprocess,sys,types
if not getattr(sys,'_navigation_baseline_loaded',False):
    for name in ('crm_automation_store','crm_automation_ui','crm_automation_home'):
        source=subprocess.check_output(['git','show','edbeb70:'+name+'.py'],text=True,encoding='utf-8')
        module=types.ModuleType(name);module.__file__=str(Path(name+'.py').resolve())
        sys.modules[name]=module
        exec(compile(source,module.__file__,'exec'),module.__dict__)
    sys._navigation_baseline_loaded=True
fixture=Path('tests/fixtures/crm_automation_preview.py')
exec(compile(fixture.read_text(encoding='utf-8'),str(fixture.resolve()),'exec'))
