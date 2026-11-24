"""Populated Marketplace browser acceptance in the reviewed Docker boundary only."""
import argparse
import hashlib
import io
import json
import statistics
from pathlib import Path
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts' / 'studio'))
import preview_runtime
import preview_export
import studio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--reference', help='Reconstruct the pre-repair store from this exact Git object')
    args = parser.parse_args()
    folder = ROOT / 'output' / 'marketplace-speed' / args.label
    folder.mkdir(parents=True, exist_ok=False)

    def source():
        archive, manifest = preview_export.capture(studio.DEFAULT_HOME, args.id, args.owner)
        # These versioned public site assets are the only additions to the
        # reviewed export. Never transfer tests, runtime data or host settings.
        names = studio.git(ROOT, 'ls-files', 'static/marketplace').splitlines()
        stream = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(archive)) as original, tarfile.open(fileobj=stream, mode='w') as target:
            for entry in original:
                if args.reference and entry.name == 'source/marketplace_store.py':
                    data = subprocess.run(['git', 'show', args.reference + ':marketplace_store.py'], cwd=ROOT,
                                          capture_output=True, check=True, timeout=15).stdout
                    data, _ = preview_export.sanitise_source('marketplace_store.py', data)
                    entry.size = len(data)
                    target.addfile(entry, io.BytesIO(data))
                    manifest['reference_store'] = {'revision': args.reference, 'sha256': hashlib.sha256(data).hexdigest()}
                    next(f for f in manifest['files'] if f['path'] == 'marketplace_store.py')['sha256'] = hashlib.sha256(data).hexdigest()
                else:
                    target.addfile(entry, original.extractfile(entry))
            for name in names:
                if Path(name).suffix not in {'.css', '.js', '.json', '.svg', '.webp'}:
                    raise ValueError('Unreviewed Marketplace asset type')
                data = preview_export.raw_source(ROOT, name)
                if len(data) > 2_000_000:
                    raise ValueError('Oversized Marketplace asset')
                if Path(name).suffix != '.webp' and studio.secret_findings(data.decode('utf-8')):
                    raise ValueError('Potential credential in public asset')
                info = tarfile.TarInfo('source/' + name)
                info.size, info.uid, info.gid, info.mode = len(data), 65532, 65532, 0o644
                target.addfile(info, io.BytesIO(data))
                manifest['files'].append({'path': name, 'sha256': hashlib.sha256(data).hexdigest(), 'synthetic_override': False})
        return stream.getvalue(), manifest

    runtime = preview_runtime.Preview(studio.DEFAULT_HOME, args.id, args.owner, source_provider=source)
    evidence = {'commit': studio.git(ROOT, 'rev-parse', 'HEAD'), 'phase2_verified': False,
                'functional_checks_passed': False, 'purpose': 'marketplace-photo-reuse',
                'reference_revision': args.reference,
                'harness_sha256': {name: hashlib.sha256((ROOT / 'scripts' / name).read_bytes()).hexdigest()
                                   for name in ('marketplace_speed_contract.py', 'verify_marketplace_speed.py')}}
    try:
        runtime.start()
        evidence['policy'] = runtime.evidence
        evidence['source_manifest'] = runtime.manifest
        # Reuse the proven boundary and its private PostgreSQL, then release the
        # idle OS preview/browser before starting the Marketplace browser. Both
        # workloads otherwise exceed this container's deliberately bounded PIDs.
        runtime._docker('exec', runtime.container_id, 'python', '-B', '-c',
            "import os,signal,pathlib; me=os.getpid(); "
            "targets=[int(p.name) for p in pathlib.Path('/proc').iterdir() if p.name.isdigit() "
            "and int(p.name)!=me and any(s in (p/'cmdline').read_bytes() for s in "
            "(b'import controller',b'streamlit',b'chrome',b'playwright/driver'))]; "
            "[(os.kill(p,signal.SIGTERM) if pathlib.Path('/proc',str(p)).exists() else None) for p in targets]")
        result = subprocess.run(['docker', '--context', runtime.docker_context, 'exec', '-i',
                                 runtime.container_id, 'python', '-B', '-'],
                                input=(ROOT / 'scripts/marketplace_speed_contract.py').read_bytes(),
                                capture_output=True, timeout=240, **studio.quiet_process())
        (folder / 'contract.log').write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('Marketplace acceptance failed: ' + (result.stdout + result.stderr).decode(errors='replace')[-4000:])
        line = next(line for line in result.stdout.splitlines() if line.startswith(b'MARKETPLACE_RESULT='))
        evidence.update(json.loads(line.split(b'=', 1)[1]))
        # Screenshots contain generated fixtures only; keep outside compact reports.
        import base64
        frames = json.loads(runtime._docker('exec', runtime.container_id, 'python', '-B', '-c',
            "import pathlib,json,base64;print(json.dumps({p.name:base64.b64encode(p.read_bytes()).decode() "
            "for p in pathlib.Path('/tmp/marketplace-evidence').glob('*.png')}))").stdout)
        if len(frames) != 4:
            raise RuntimeError('Four desktop/mobile screenshots required')
        for name, encoded in frames.items():
            (folder / name).write_bytes(base64.b64decode(encoded))
        if args.baseline:
            baseline = json.loads(args.baseline.read_text())
            assert evidence['screenshots'] == baseline['screenshots'], 'Desktop/mobile appearance changed'
            assert all(c['provider'] == 0 for c in evidence['warm_costs']), 'Warm provider work remains'
            assert evidence['concurrent_costs']['provider'] == 1, 'Duplicate concurrent provider work remains'
            assert evidence['three_tab_costs']['provider'] == 12, 'Duplicate multi-tab provider work remains'
            assert evidence['soak_costs']['provider'] == 0, 'Repeat-read soak downloaded media again'
            before, after = map(statistics.median, [baseline['warm_samples_ms'], evidence['warm_samples_ms']])
            assert after <= before * .8, 'Warm workflow improvement below 20%'
            assert statistics.median(evidence['cold_samples_ms']) <= statistics.median(baseline['cold_samples_ms']) * 1.15, 'Cold workflow regressed'
            evidence.update(baseline_samples_ms=baseline['warm_samples_ms'], candidate_samples_ms=evidence['warm_samples_ms'],
                            behaviour_preserved=True, improvement_ms=round(before-after,3), improvement_percent=round((before-after)/before*100,2))
        evidence['phase2_verified'] = True
        evidence['functional_checks_passed'] = True
        print(json.dumps({k: v for k, v in evidence.items() if k not in {'policy', 'source_manifest'}}, indent=2))
    finally:
        try:
            for attempt in range(30):
                try:
                    runtime.stop()
                    evidence['cleanup_complete'] = True
                    break
                except RuntimeError as error:
                    if not str(error).startswith('Registry occupied.') or attempt == 29:
                        raise
                    time.sleep(1)
        finally:
            studio.atomic(folder / 'acceptance.json', evidence)


if __name__ == '__main__':
    main()
