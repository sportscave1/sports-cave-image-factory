"""Run populated Reporting acceptance inside the reviewed, network-none preview."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/studio'))
import preview_runtime
import studio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    folder = ROOT / 'output/reporting-speed' / args.label
    folder.mkdir(parents=True, exist_ok=False)
    runtime = preview_runtime.Preview(studio.DEFAULT_HOME, args.id, args.owner)
    evidence = dict(commit=studio.git(ROOT, 'rev-parse', 'HEAD'), base=args.base,
                    phase2_verified=False, functional_checks_passed=False)
    try:
        runtime.start()
        evidence['policy'] = runtime.evidence
        evidence['source_manifest'] = runtime.manifest
        evidence['harness_sha256'] = {name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes()).hexdigest()
            for name in ('verify_reporting_speed.py','reporting_speed_contract.py','reporting_speed_fixture.py')}
        runtime._docker('exec', runtime.container_id, 'python', '-B', '-c',
            "import os,signal,pathlib; me=os.getpid(); "
            "targets=[int(p.name) for p in pathlib.Path('/proc').iterdir() if p.name.isdigit() "
            "and int(p.name)!=me and any(s in (p/'cmdline').read_bytes() for s in "
            "(b'import controller',b'streamlit',b'chrome',b'playwright/driver'))]; "
            "[(os.kill(p,signal.SIGTERM) if pathlib.Path('/proc',str(p)).exists() else None) for p in targets]")
        modules = {'baseline_dashboard.py': subprocess.check_output(
            ['git', 'show', args.base + ':sports_cave_dashboard.py'], cwd=ROOT).decode('utf-8'),
            'sports_cave_dashboard.py': (ROOT / 'sports_cave_dashboard.py').read_text(encoding='utf-8-sig')}
        modules['reporting_speed_fixture.py'] = (ROOT / 'scripts/reporting_speed_fixture.py').read_text()
        payload = 'MODULES = ' + repr(modules) + '\n' + (ROOT / 'scripts/reporting_speed_contract.py').read_text()
        result = subprocess.run(['docker', '--context', runtime.docker_context, 'exec', '-i',
                                 runtime.container_id, 'python', '-B', '-'], input=payload.encode(),
                                capture_output=True, timeout=300, **studio.quiet_process())
        (folder / 'contract.log').write_bytes(result.stdout + result.stderr)
        import base64
        frames = json.loads(runtime._docker('exec', runtime.container_id, 'python', '-B', '-c',
            "import pathlib,json,base64;print(json.dumps({p.name:base64.b64encode(p.read_bytes()).decode() "
            "for p in pathlib.Path('/tmp/reporting-evidence').glob('*.png')}))").stdout)
        for name, encoded in frames.items():
            (folder / name).write_bytes(base64.b64decode(encoded))
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr).decode(errors='replace')[-4500:])
        packet = next(line for line in result.stdout.splitlines() if line.startswith(b'REPORTING_RESULT='))
        evidence.update(json.loads(packet.split(b'=', 1)[1]))
        evidence.update(phase2_verified=True, functional_checks_passed=True)
        print(json.dumps({k: v for k, v in evidence.items() if k not in {'policy','source_manifest'}}, indent=2))
    finally:
        try:
            runtime.stop()
            evidence['cleanup_complete'] = True
        finally:
            studio.atomic(folder / 'acceptance.json', evidence)


if __name__ == '__main__':
    main()
