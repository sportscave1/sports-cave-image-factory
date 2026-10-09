"""Offline image-workflow regression runner; each suite gets a fresh process."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


PATTERNS = (
    'test_ads_*.py', 'test_carousel*.py', 'test_design_studio*.py',
    'test_mockup*.py', 'test_social_media*.py', 'test_sports_cave_prompt_blocks.py',
    'test_physical_frame_realism.py', 'test_premium_image_quality_v3.py',
    'test_prompt_store.py', 'test_marketing_factory_page.py',
    'test_crm_email_prompt.py', 'test_crm_image_*.py', 'test_crm_prompt_helper.py',
    'test_product_upload_prompts.py', 'test_posting*.py',
    'test_meta_carousel*.py', 'test_meta_review_creative.py', 'test_meta_review_products.py',
    'test_meta_posting*.py', 'test_sidebar_theme.py', 'test_sidebar_navigation_cleanup.py',
    'test_seo_blog_workflow.py',
)


def child_suite(pattern):
    """Fail on accidental live access; test-owned mocks and loopback remain usable."""
    import socket
    import unittest
    import dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: False
    connect = socket.socket.connect
    def offline_connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {'127.0.0.1', '::1', 'localhost'}:
            raise RuntimeError('Image regression tests must not contact live services')
        return connect(sock, address)
    socket.socket.connect = offline_connect
    suite = unittest.defaultTestLoader.discover('tests', pattern=pattern)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return not result.wasSuccessful()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', action='append', help='Run a specific test filename (repeatable)')
    parser.add_argument('--output', default='tmp/image-prompt-quality')
    args = parser.parse_args()
    suites = sorted(set(args.suite or [p.name for pattern in PATTERNS for p in Path('tests').glob(pattern)]))
    if not suites:
        parser.error('No suites found; run from the repository root')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'}
    for suite in suites:
        if not (Path('tests') / suite).is_file():
            parser.error(f'Missing suite: {suite}')
        run = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child', suite],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        text = run.stdout.decode('utf-8', errors='replace')
        (output / (Path(suite).stem + '.log')).write_text(text, encoding='utf-8')
        count = re.search(r'^Ran (\d+) tests? in ', text, re.M)
        tally = {key: int(value) for key, value in re.findall(r'(failures|errors|skipped)=(\d+)', text)}
        row = {'suite': suite, 'tests': int(count[1]) if count else 0, 'exit_code': run.returncode, **tally}
        rows.append(row)
        print(json.dumps(row), flush=True)
        if run.returncode:
            for line in text.splitlines():
                if line.startswith(('FAIL:', 'ERROR:', 'FAILED', 'ModuleNotFoundError:')):
                    print(line[:400], flush=True)
    summary = {key: sum(row.get(key, 0) for row in rows) for key in ('tests', 'failures', 'errors', 'skipped')}
    summary['passed'] = summary['tests'] - sum(summary[key] for key in ('failures', 'errors', 'skipped'))
    summary['failed_suites'] = [row['suite'] for row in rows if row['exit_code']]
    (output / 'summary.json').write_text(json.dumps({'summary': summary, 'suites': rows}, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary), flush=True)
    return bool(summary['failed_suites'])


if __name__ == '__main__':
    # Put the checkout root first for script execution as well as module execution.
    sys.path.insert(0, str(Path.cwd()))
    sys.exit(child_suite(sys.argv[2]) if len(sys.argv) == 3 and sys.argv[1] == '--child' else main())
