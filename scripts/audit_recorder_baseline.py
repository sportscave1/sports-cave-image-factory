"""Read-only installed recorder audit; never starts a helper or reads user recordings."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(install, source):
    selected = (install / 'active.txt').read_text(encoding='utf-8-sig').strip()
    if not re.fullmatch(r'(?:[a-f0-9]{20}|[a-f0-9]{64})', selected):
        raise ValueError('Unsupported installed selector; no release files inspected.')
    app = install / 'releases' / selected / 'app'
    manifest = json.loads((app / 'recorder-package.json').read_text(encoding='utf-8-sig'))
    failures = []
    for name, expected in manifest['files'].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe package manifest path')
        path = app.joinpath(*relative.parts)
        if not path.is_file() or path.stat().st_size != expected['size'] or sha(path) != expected['sha256']:
            failures.append(name)
    build = json.loads((app / 'desktop_recorder/bin/build-manifest.json').read_text(encoding='utf-8-sig'))
    differences = []
    for name, expected in build['sources'].items():
        if Path(name).name != name:
            raise ValueError('Unsafe native source name')
        path = source / 'windows-screen-recorder/native' / name
        if not path.is_file() or sha(path) != expected:
            differences.append(name)
    previous = (install / 'previous.txt').read_text(encoding='utf-8-sig').strip()
    previous_valid = bool(re.fullmatch(r'(?:[a-f0-9]{20}|[a-f0-9]{64})', previous))
    return dict(
        selected_release=selected,
        package_protocol=manifest['protocol'], package_format_version=manifest['version'],
        checked_file_count=len(manifest['files']), integrity_failures=failures,
        native_sha256=sha(app / 'desktop_recorder/bin/DesktopRecorder.exe'),
        build=build, compared_source=str(source), native_source_differences=differences,
        adapter_version=json.loads((app / 'edge-adapter/manifest.json').read_text())['version'],
        previous_release=previous if previous_valid else 'unsupported selector',
        rollback_files_present=previous_valid and (install / 'releases' / previous / 'app/recorder-package.json').is_file(),
        physical_replay_verified=False,
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', required=True, type=Path)
    parser.add_argument('--source', required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.install.resolve(), args.source.resolve())
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result['integrity_failures'] else 0)
