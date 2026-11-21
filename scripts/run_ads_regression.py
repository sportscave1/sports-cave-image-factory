"""Run Ads and queue regressions without inherited production credentials.

Set AUTO_EDITIONS_TEST_PGLITE to a local @electric-sql/pglite/dist/index.js.
Browser tests require Playwright and a local Edge/Chromium installation.
"""
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main():
    pglite = os.environ.get('AUTO_EDITIONS_TEST_PGLITE', '')
    if not pglite or not Path(pglite).is_file():
        raise SystemExit('Set AUTO_EDITIONS_TEST_PGLITE to an installed local PGlite dist/index.js.')
    allowed = {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'PATHEXT',
               'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'PROGRAMFILES',
               'PROGRAMFILES(X86)', 'PROGRAMDATA', 'NODE_PATH'}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env['AUTO_EDITIONS_TEST_PGLITE'] = pglite
    env['PYTHONPATH'] = os.pathsep.join((str(ROOT / 'tests'), str(ROOT)))
    tests = sorted(str(path.relative_to(ROOT)) for path in (ROOT / 'tests').glob('test_ads*.py'))
    tests += ['tests/test_ad_quick_picker_browser.py', 'tests/test_design_publish_ad.py',
              'tests/test_product_upload_staff_queue.py']
    result = subprocess.run([sys.executable, '-m', 'pytest', '-p', 'ads_offline_guard',
                             *tests, '-q', '--tb=no', *sys.argv[1:]], cwd=ROOT, env=env)
    if result.returncode:
        return result.returncode
    scripts = ['ads_popup_delete', 'ads_companion_downloads', 'ads_refresh_reference',
               'companion_status_polling', 'ads_handoff_status', 'top_bar_requests', 'top_bar_navigation']
    return subprocess.run(['node', '--test', *[f'tests/test_{name}.cjs' for name in scripts]],
                          cwd=ROOT, env=env).returncode


if __name__ == '__main__':
    sys.exit(main())
