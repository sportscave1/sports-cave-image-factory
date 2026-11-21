"""Run Phase 1 contracts in a disposable, network-isolated local container.

Run with the provisioned release Python (pytest dependencies), from this task.
No app credentials, host mounts, provider access or published ports are used.
"""
import hashlib
import argparse
import importlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'sha256:b1857ed93a713747038020d59353d04ccab683b126c0b5dd782368dc6054ed17'
TESTS = ['companion_header', 'companion_display_resilience', 'companion_backlog_scale',
         'design_deletion_status', 'product_upload_generation_status', 'meta_posting_progress',
         'ads_companion_controls', 'ads_companion_transfer', 'companion_phase5', 'companion_phase4',
         'product_upload_jobs', 'product_upload_staff_queue', 'morning_design_queue',
         'companion_header_browser', 'status_phase1_history', 'companion_status_payload', 'auto_editions_header']


def call(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, capture_output=True, check=True, timeout=180, **kwargs).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase3-only', action='store_true')
    args = parser.parse_args()
    name = 'sc-status-phase1-' + uuid.uuid4().hex[:10]
    output = ROOT / 'output/status-speed-audit' / name
    output.mkdir(parents=True)
    archive = call(['git', 'archive', 'HEAD'])
    extra = io.BytesIO()
    hashes = {}
    with tarfile.open(fileobj=extra, mode='w') as tar:
        # Only task-selected tests and runtime files supplement the committed archive.
        files = ['tests/test_' + n + '.py' for n in TESTS] + [
            'tests/status_phase1_history.py', 'tests/status_phase1_postgres.py',
            'tests/status_phase1_browser.py', 'tests/test_auto_editions_jobs.py',
            'tests/status_phase1_queue_baseline.py', 'tests/status_phase2_browser.py',
            'companion_status_payload.py', 'product_upload_staff_queue.py',
            'components/sports_cave_top_bar/index.html', 'windows-upload-companion/composer.js',
            'tests/status_phase3_browser.py', 'windows-upload-companion/manifest.json', 'scripts/soak_companion_display.py']
        for file in files:
            value = (ROOT / file).read_bytes()
            hashes[file] = hashlib.sha256(value).hexdigest()
            tar.add(ROOT / file, arcname='audit/' + file)
        baseline = call(['git', 'show', '58569c66:product_upload_artwork.py'])
        item = tarfile.TarInfo('baseline.py'); item.size = len(baseline)
        tar.addfile(item, io.BytesIO(baseline))
        header = call(['git', 'show', 'HEAD:components/sports_cave_top_bar/index.html'])
        item = tarfile.TarInfo('header-baseline.html'); item.size = len(header)
        tar.addfile(item, io.BytesIO(header))
        composer = call(['git', 'show', 'HEAD:windows-upload-companion/composer.js'])
        item = tarfile.TarInfo('composer-baseline.js'); item.size = len(composer)
        tar.addfile(item, io.BytesIO(composer))
        for module in ('pytest', '_pytest', 'pluggy', 'packaging', 'iniconfig', 'pygments', 'py'):
            path = Path(importlib.import_module(module).__file__)
            path = path.parent if path.name == '__init__.py' else path
            tar.add(path, arcname='deps/' + (module if path.is_dir() else path.name),
                    filter=lambda item: None if '__pycache__' in item.name else item)
    metadata = dict(base_sha=call(['git', 'rev-parse', 'HEAD']).decode().strip(), image=IMAGE,
                    test_sha256=hashes, baseline_sha256=hashlib.sha256(baseline).hexdigest())
    (output / 'manifest.json').write_text(json.dumps(metadata, indent=2))
    try:
        call(['docker', 'run', '-d', '--name', name, '--network', 'none', '--read-only',
              '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--user', '65532:65532',
              '--memory', '2g', '--cpus', '2', '--pids-limit', '256', '--tmpfs',
              '/tmp:rw,nosuid,nodev,size=1g,mode=1777', '--entrypoint', 'sleep', IMAGE, '600'])
        call(['docker', 'exec', '-i', name, 'sh', '-c', 'mkdir /tmp/audit && tar -xf - -C /tmp/audit'], input=archive)
        call(['docker', 'exec', '-i', name, 'tar', '-xf', '-', '-C', '/tmp'], input=extra.getvalue())
        call(['docker', 'exec', name, 'sh', '-c',
              '/usr/lib/postgresql/15/bin/initdb -D /tmp/pg -A trust -U studio >/tmp/init.log && '
              '/usr/lib/postgresql/15/bin/pg_ctl -D /tmp/pg -l /tmp/pg.log '
              '-o "-h 127.0.0.1 -p 55432 -k /tmp" start'])
        env = ['-e', 'HOME=/tmp', '-e', 'PYTHONPATH=/tmp/deps:/tmp/audit:/tmp/audit/tests',
               '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD=1',
               '-e', 'STATUS_PHASE1_ISOLATED_POSTGRES=1', '-e', 'STATUS_TEST_ARTWORK_BASELINE=/tmp/baseline.py',
               '-e', 'STATUS_TEST_BROWSER_CHANNEL=', '-e', 'PLAYWRIGHT_BROWSERS_PATH=/opt/browsers']
        command = ['docker', 'exec', '-w', '/tmp/audit', *env, name]
        commands = [('contracts.log', ['python', '-B', '-m', 'pytest', '-q',
                '-o', 'cache_dir=/tmp/pytest-cache', *['tests/test_' + n + '.py' for n in TESTS], '--durations=10']),
                ('browser-baseline.json', ['python', '-B', 'tests/status_phase1_browser.py']),
                ('queue-baseline.json', ['python', '-B', 'tests/status_phase1_queue_baseline.py']),
                ('phase2-browser.json', ['python', '-B', 'tests/status_phase2_browser.py'])]
        if args.phase3_only:
            commands = []
        commands.append(('phase3-browser.json', ['python', '-B', 'tests/status_phase3_browser.py', 'windows-upload-companion/manifest.json', 'scripts/soak_companion_display.py']))
        for filename, command_args in commands:
            result = subprocess.run(command + command_args, capture_output=True, cwd=ROOT, timeout=180)
            (output / filename).write_bytes(result.stdout)
            (output / (filename + '.stderr')).write_bytes(result.stderr)
            result.check_returncode()
            if filename == 'contracts.log' and b' skipped' in result.stdout:
                raise RuntimeError('Phase 1 requires executed contracts; skipped checks are incomplete')
        print(json.dumps(dict(status='passed', evidence=str(output))))
    finally:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=30)


if __name__ == '__main__':
    main()
