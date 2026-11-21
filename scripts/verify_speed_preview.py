"""Opt-in Speed acceptance inside the existing hardened synthetic Docker boundary."""
import argparse
import base64
import io
import json
from pathlib import Path
import re
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
    parser.add_argument('--meta-baseline', help='Exact previous Git revision for the Meta Review speed check')
    args = parser.parse_args()
    folder = ROOT / '.local-data' / 'speed' / 'preview'
    folder.mkdir(parents=True, exist_ok=True)
    runtime = preview_runtime.Preview(studio.DEFAULT_HOME, args.id, args.owner)
    evidence = {'commit': studio.git(ROOT, 'rev-parse', 'HEAD'), 'phase2_verified': False,
                'functional_checks_passed': False, 'purpose': 'installation', 'started_at': studio.now()}
    def event(data):
        # Another Studio task can briefly hold the shared registry. Scope checks
        # fail before dispatching these non-inspection events, so bounded retry
        # cannot repeat a click or bypass ownership validation.
        for attempt in range(30):
            try:
                return runtime.event(data)
            except RuntimeError as error:
                if not str(error).startswith('Registry occupied.') or attempt == 29:
                    raise
                time.sleep(1)

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
        capture('login', event({'action': 'login-synthetic'}))
        frame = event({'action': 'navigate', 'page': 'speed_optimisation'})
        capture('speed-desktop', frame)
        if ('Synthetic preview fixture' not in frame.get('text', '')
                or 'Traceback' in frame.get('text', '') or 'currently unavailable' in frame.get('text', '')):
            raise AssertionError('Speed page did not render successfully.')
        event({'action': 'size', 'mode': 'mobile'})
        # Let the normal responsive drawer transition settle before capturing.
        capture('speed-mobile', event({'action': 'frame'}))
        if args.meta_baseline:
            if not re.fullmatch('[a-f0-9]{40}', args.meta_baseline):
                raise ValueError('Pin the exact baseline Git revision')
            baseline = subprocess.check_output(['git', 'show', args.meta_baseline + ':meta_review_live.py'], cwd=ROOT)
            payload = {'baseline.py': baseline.decode(),
                       'benchmark_meta_review_speed.py': (ROOT / 'scripts/benchmark_meta_review_speed.py').read_text()}
            transfer = subprocess.run(['docker', '--context', runtime.docker_context, 'exec', '-i',
                runtime.container_id, 'python', '-B', '-c',
                "import sys,json,pathlib;p=pathlib.Path('/tmp/meta_speed');p.mkdir();[(p/n).write_text(v) for n,v in json.load(sys.stdin).items()]"],
                input=json.dumps(payload).encode(), capture_output=True, timeout=30, **studio.quiet_process())
            transfer.check_returncode()
            for script, marker, timeout in (
                    ("import sys;sys.path[:0]=['/tmp/source','/tmp/meta_speed'];import benchmark_meta_review_speed as b;import json;print('META_SPEED_RESULT='+json.dumps(b.run('/tmp/meta_speed/baseline.py')))", 'META_SPEED_RESULT=', 120),):
                result = subprocess.run(['docker', '--context', runtime.docker_context, 'exec', '-i',
                    runtime.container_id, 'python', '-B', '-c', script], capture_output=True, timeout=timeout, **studio.quiet_process())
                if result.returncode:
                    raise RuntimeError('Meta synthetic check failed: ' + result.stderr.decode()[-3000:])
                value = json.loads(next(line[len(marker):] for line in result.stdout.decode().splitlines() if line.startswith(marker)))
                evidence['meta_speed'] = value
            # Reuse the existing isolated OS/browser instead of launching another
            # Chromium/Streamlit pair beyond the fixed process/memory boundary.
            browser_fixture = '''import sys
from pathlib import Path
assert Path('/opt/studio/entry.py').is_file()
assert {p.name for p in Path('/sys/class/net').iterdir()} == {'lo'}
sys.path.insert(0,'/tmp/meta_speed')
import benchmark_meta_review_speed as b
import ads_meta_review_page as p
import streamlit as st
module = b.baseline_module('/tmp/meta_speed/baseline.py') if Path('/tmp/meta_speed/variant').read_text()=='baseline' else b.live
p.live=module
p.meta.get_meta_config=lambda:b.CONFIG
p.meta._request=b.Fixture(delay=False).request
p.recency.load=lambda *a,**k:{'available':False}
p.datetime=module.datetime=b.FixedDateTime
st.session_state.pop('meta-review-live-cache',None)
'''
            update = """import json,sys,pathlib
p=pathlib.Path('/tmp/source/app.py');original=pathlib.Path('/tmp/meta_speed/original_app.py')
if not original.exists():original.write_bytes(p.read_bytes())
fixture,variant=json.load(sys.stdin)
pathlib.Path('/tmp/meta_speed/fixture.py').write_text(fixture)
pathlib.Path('/tmp/meta_speed/variant').write_text(variant)
p.write_text(\"exec(compile(open('/tmp/meta_speed/fixture.py').read(), 'synthetic-meta-fixture', 'exec'))\\n\"+original.read_text())
"""
            frames = {}
            for variant in ('baseline', 'candidate'):
                changed = subprocess.run(['docker', '--context', runtime.docker_context, 'exec', '-i',
                    runtime.container_id, 'python', '-B', '-c', update], input=json.dumps([browser_fixture, variant]).encode(),
                    capture_output=True, timeout=15, **studio.quiet_process())
                changed.check_returncode()
                event({'action': 'size', 'mode': 'desktop'})
                event({'action': 'refresh'})
                event({'action': 'navigate', 'page': 'ads_meta_review'})
                for mode in ('desktop', 'mobile'):
                    event({'action': 'size', 'mode': mode})
                    frame = event({'action': 'frame'})
                    # Streamlit's canvas table does not expose row text through
                    # body.innerText. Populated rows are checked by AppTest above;
                    # here require the completed LIVE screen and compare pixels.
                    if ('LIVE META' not in frame['text'] or 'Refresh From Meta' not in frame['text']
                            or 'Traceback' in frame['text']):
                        raise AssertionError('Populated Meta Review browser render failed')
                    capture('meta-' + variant + '-' + mode, frame)
                    frames[(variant, mode)] = frame
            from PIL import Image, ImageChops
            differences = {}
            for mode in ('desktop', 'mobile'):
                before, after = (frames[(variant, mode)] for variant in ('baseline', 'candidate'))
                if before['text'] != after['text']:
                    raise AssertionError('Meta Review browser content changed: ' + mode)
                a, b = (Image.open(io.BytesIO(base64.b64decode(frame['image']))).convert('RGB')
                        for frame in (before, after))
                if a.size != b.size:
                    raise AssertionError('Meta Review viewport changed: ' + mode)
                delta = ImageChops.difference(a, b)
                maximum = max(high for _, high in delta.getextrema())
                changed_pixels = sum(pixel != (0, 0, 0) for pixel in delta.getdata())
                fraction = changed_pixels / (a.width * a.height)
                # The controller transports JPEG. Allow only near-identical
                # compression/antialias noise, never layout or content changes.
                if maximum > 2 or fraction > .0005:
                    raise AssertionError('Meta Review browser pixels changed: ' + mode)
                differences[mode] = {'maximum_channel_delta': maximum, 'changed_pixel_fraction': fraction}
            evidence['meta_browser'] = {'visual_parity': True, 'synthetic_override': True,
                'viewports': ['desktop', 'mobile'], 'route': 'ads_meta_review', 'jpeg_noise': differences}
            evidence.update(purpose='performance', baseline_commit=args.meta_baseline, behaviour_preserved=True,
                baseline_samples_ms=evidence['meta_speed']['baseline_workflow']['samples_ms'],
                candidate_samples_ms=evidence['meta_speed']['candidate_workflow']['samples_ms'])
            print(json.dumps({'stage': 'meta-speed', 'baseline_samples_ms': evidence['baseline_samples_ms'],
                              'candidate_samples_ms': evidence['candidate_samples_ms'],
                              'visual_parity': evidence['meta_browser']['visual_parity']}), flush=True)
        evidence['phase2_verified'] = True
        evidence['functional_checks_passed'] = True
        evidence['source_manifest'] = runtime.manifest
    except Exception as error:
        evidence['failure_type'] = type(error).__name__
        if runtime.container_id:
            try:
                capture('failure', event({'action': 'frame'}))
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
