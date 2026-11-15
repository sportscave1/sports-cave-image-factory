"""Read-only comparison against the reported regression revision; loopback only."""
from pathlib import Path
import subprocess,sys,types
for name in ('crm_automation_ui','crm_automation_home','crm_automation_analytics_ui'):
    source=subprocess.check_output(['git','show','43b37ea:'+name+'.py'],text=True,encoding='utf-8')
    module=types.ModuleType(name);module.__file__=str(Path(name+'.py').resolve())
    sys.modules[name]=module
    exec(compile(source,module.__file__,'exec'),module.__dict__)
fixture=Path('tests/fixtures/crm_automation_preview.py')
exec(compile(fixture.read_text(encoding='utf-8'),str(fixture.resolve()),'exec'))
