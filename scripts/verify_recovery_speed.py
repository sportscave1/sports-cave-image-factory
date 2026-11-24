"""Run populated recovery planning acceptance only in reviewed Docker isolation."""
import argparse
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
    folder = ROOT / 'output/recovery-speed' / args.label
    folder.mkdir(parents=True, exist_ok=False)
    runtime = preview_runtime.Preview(studio.DEFAULT_HOME, args.id, args.owner)
    evidence = {'commit': studio.git(ROOT, 'rev-parse', 'HEAD'), 'base': args.base,
                'phase2_verified': False, 'functional_checks_passed': False}
    try:
        runtime.start()
        evidence['policy'] = runtime.evidence
        # Release idle OS/browser PIDs before the background planning workload.
        # This is the exact owned container; its private PostgreSQL stays alive.
        runtime._docker('exec', runtime.container_id, 'python', '-B', '-c',
            "import os,signal,pathlib; me=os.getpid(); "
            "targets=[int(p.name) for p in pathlib.Path('/proc').iterdir() if p.name.isdigit() "
            "and int(p.name)!=me and any(s in (p/'cmdline').read_bytes() for s in "
            "(b'import controller',b'streamlit',b'chrome',b'playwright/driver'))]; "
            "[(os.kill(p,signal.SIGTERM) if pathlib.Path('/proc',str(p)).exists() else None) for p in targets]")
        # Read models and hash dependencies only; never execute a worker.
        names = ('worker_health.py', 'worker_diagnostics.py', 'recovery_revision_cache.py', 'scripts/studio/auto_editions_local.py')
        modules = {name: (ROOT / name).read_text(encoding='utf-8-sig') for name in names}
        modules['baseline_recovery.py'] = subprocess.check_output(
            ['git', 'show', args.base + ':auto_editions_recovery.py'], cwd=ROOT).decode('utf-8')
        modules['auto_editions_recovery.py'] = (ROOT / 'auto_editions_recovery.py').read_text(encoding='utf-8-sig')
        payload = 'MODULES = ' + repr(modules) + '\n' + (ROOT / 'scripts/recovery_speed_contract.py').read_text()
        result = subprocess.run(['docker', '--context', runtime.docker_context, 'exec', '-i',
                                 runtime.container_id, 'python', '-B', '-'], input=payload.encode(),
                                capture_output=True, timeout=240, **studio.quiet_process())
        (folder / 'contract.log').write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr).decode(errors='replace')[-3500:])
        packet = next(line for line in result.stdout.splitlines() if line.startswith(b'RECOVERY_RESULT='))
        evidence.update(json.loads(packet.split(b'=', 1)[1]))
        evidence.update(phase2_verified=True, functional_checks_passed=True)
        print(json.dumps({k: v for k, v in evidence.items() if k != 'policy'}, indent=2))
    finally:
        try:
            runtime.stop()
            evidence['cleanup_complete'] = True
        finally:
            studio.atomic(folder / 'acceptance.json', evidence)


if __name__ == '__main__':
    main()
