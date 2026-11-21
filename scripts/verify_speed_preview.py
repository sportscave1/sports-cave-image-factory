"""Opt-in Speed acceptance inside the existing hardened synthetic Docker boundary."""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts' / 'studio'))
import preview_runtime
import studio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', required=True)
    parser.add_argument('--owner', required=True)
    args = parser.parse_args()
    folder = ROOT / '.local-data' / 'speed' / 'preview'
    folder.mkdir(parents=True, exist_ok=True)
    runtime = preview_runtime.Preview(studio.DEFAULT_HOME, args.id, args.owner)
    evidence = {'commit': studio.git(ROOT, 'rev-parse', 'HEAD'), 'phase2_verified': False,
                'functional_checks_passed': False, 'purpose': 'installation', 'started_at': studio.now()}
    def capture(name, frame):
        (folder / (name + '.jpg')).write_bytes(base64.b64decode(frame['image']))
        (folder / (name + '.txt')).write_text(frame.get('text', ''), encoding='utf-8')
        print(json.dumps({'stage': name, 'text': frame.get('text', '')[:1000]}), flush=True)
    try:
        capture('startup', runtime.start())
        evidence['policy'] = runtime.evidence
        check = subprocess.run(['docker', '--context', runtime.docker_context, 'exec', '-i',
                                runtime.container_id, 'python', '-B', '-'],
                               input=(ROOT / 'scripts/speed_preview_contract.py').read_bytes(),
                               capture_output=True, timeout=60, **studio.quiet_process())
        if check.returncode:
            raise RuntimeError('Synthetic PostgreSQL/API checks failed: ' + check.stderr.decode()[-2000:])
        result = next(line.removeprefix(b'SPEED_ACCEPTANCE_RESULT=') for line in check.stdout.splitlines()
                      if line.startswith(b'SPEED_ACCEPTANCE_RESULT='))
        evidence['contracts'] = json.loads(result)
        print(json.dumps({'stage': 'postgres-api', **evidence['contracts']}), flush=True)
        capture('login', runtime.event({'action': 'login-synthetic'}))
        frame = runtime.event({'action': 'navigate', 'page': 'speed_optimisation'})
        capture('speed-desktop', frame)
        if ('Synthetic preview fixture' not in frame.get('text', '')
                or 'Traceback' in frame.get('text', '') or 'currently unavailable' in frame.get('text', '')):
            raise AssertionError('Speed page did not render successfully.')
        runtime.event({'action': 'size', 'mode': 'mobile'})
        # Let the normal responsive drawer transition settle before capturing.
        capture('speed-mobile', runtime.event({'action': 'frame'}))
        evidence['phase2_verified'] = True
        evidence['functional_checks_passed'] = True
        evidence['source_manifest'] = runtime.manifest
    except Exception as error:
        evidence['failure_type'] = type(error).__name__
        if runtime.container_id:
            try:
                capture('failure', runtime.event({'action': 'frame'}))
                logs = runtime._docker('exec', runtime.name, 'cat', '/tmp/application.log', check=False).stdout
                (folder / 'synthetic-application.log').write_text(logs, encoding='utf-8')
                print(logs[-5000:], flush=True)
            except Exception:
                pass
        raise
    finally:
        for attempt in range(30):
            try:
                runtime.stop()
                break
            except RuntimeError as error:
                if not str(error).startswith('Registry occupied.') or attempt == 29:
                    raise
                time.sleep(1)
        studio.atomic(folder / 'acceptance.json', evidence)


if __name__ == '__main__':
    main()
