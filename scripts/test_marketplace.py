"""Run the marketplace checks with an allowlisted, credential-free environment."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'PATHEXT',
           'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)')
env = {key: value for key, value in os.environ.items() if key.upper() in ALLOWED}
env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', STREAMLIT_BROWSER_GATHER_USAGE_STATS='false',
           PROMPTS_GITHUB_TOKEN='', RENDER_API_KEY='')
modules = ['tests.test_marketplace', 'tests.test_marketplace_media', 'tests.test_marketplace_dropbox', 'tests.test_marketplace_accounts', 'tests.test_marketplace_notifications', 'tests.test_marketplace_collation', 'tests.test_navigation_v5', 'tests.test_prompts_page']
if '--legacy' in sys.argv:
    modules.extend(['tests.test_os_accounts', 'tests.test_app_install_branding'])
result = subprocess.run([sys.executable, '-B', '-m', 'unittest', *modules, '-v'], cwd=ROOT, env=env)
raise SystemExit(result.returncode)
