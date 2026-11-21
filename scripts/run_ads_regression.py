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
    prompt_tests = sorted(str(path.relative_to(ROOT)) for path in (ROOT / 'tests').glob('test_prompt*.py')
                          if path.name not in ('test_prompt_tests.py', 'test_prompts_page.py'))
    prompt_tests += [f'tests/test_{name}.py' for name in (
        'sports_cave_prompt_blocks', 'carousel_detail_prompts', 'owner_confirmed_prompt_defaults',
        'product_upload_prompts', 'product_upload_live_edition_prompt', 'mockup_prompt_preview',
        'meta_collection_template_copy', 'product_collector_copy')]
    # Legacy upload tests import the application at collection time. Keep the
    # standalone editor's Streamlit runtime independent of those global adapters.
    groups = [('ads', tests), ('prompt-contracts', prompt_tests),
              ('prompt-editor', ['tests/test_prompt_tests.py', 'tests/test_prompts_page.py'])]
    for label, files in groups:
        args = list(sys.argv[1:])
        if label != 'ads':
            for index, arg in enumerate(args):
                if arg.startswith('--junitxml='):
                    path = Path(arg.split('=', 1)[1])
                    args[index] = '--junitxml=' + str(path.with_name(path.stem + '-' + label + path.suffix))
        result = subprocess.run([sys.executable, '-m', 'pytest', '-p', 'ads_offline_guard',
                                 *files, '-q', '--tb=no', *args], cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
    scripts = ['ads_popup_delete', 'ads_companion_downloads', 'ads_refresh_reference',
               'companion_status_polling', 'ads_handoff_status', 'top_bar_requests', 'top_bar_navigation']
    return subprocess.run(['node', '--test', *[f'tests/test_{name}.cjs' for name in scripts]],
                          cwd=ROOT, env=env).returncode


if __name__ == '__main__':
    sys.exit(main())
