"""Local integration contract and bounded projections; never stores captured text."""
import hashlib
import json
from functools import cache
from pathlib import Path
from .contract import Invalid

PROTOCOL = 2
BUILD = "local-phase5-20261022"
FRAME_BYTES = 65536


@cache
def identity():
    package = Path(__file__).resolve().parent
    native = package / 'bin' / 'DesktopRecorder.exe'
    helper_hash = hashlib.sha256()
    for source in sorted(package.glob('*.py')):
        helper_hash.update(source.name.encode())
        helper_hash.update(source.read_bytes())
    return dict(build=BUILD, ipc=PROTOCOL, recording_format=1, action_versions=[2, 3],
                adapter_protocol=1, helper_sha256=helper_hash.hexdigest(),
                native_sha256=hashlib.sha256(native.read_bytes()).hexdigest() if native.exists() else None)


def verify_adapter(adapter):
    try:
        manifest = json.loads(adapter.read_text())
        version = manifest['version']
        if version not in {'0.3.4', '0.3.5'}:
            raise ValueError('unsupported version')
        if version == '0.3.5':
            if not adapter.with_name('prepared-context.js').is_file():
                raise ValueError('missing prepared context')
            scoped = [script for script in manifest['content_scripts']
                      if 'https://sports-cave-image-factory.onrender.com/*' in script['matches']]
            if not scoped or any(script['js'].index('prepared-context.js') >=
                                 script['js'].index('browser-identity.js') for script in scoped):
                raise ValueError('invalid prepared context load order')
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise Invalid('Incompatible browser adapter package: expected complete version 0.3.4 or 0.3.5 / protocol 1.') from error


def verify_package(executable):
    executable = Path(executable)
    path = executable.parent / "build-manifest.json"
    if not path.exists():
        raise Invalid("Incompatible helper: build manifest missing. Rebuild the local candidate.")
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if manifest.get("executable_sha256") != hashlib.sha256(executable.read_bytes()).hexdigest():
        raise Invalid("Incompatible helper: executable differs from its verified build manifest.")
    adapter = Path(__file__).resolve().parents[1] / "edge-adapter" / "manifest.json"
    verify_adapter(adapter)
    return {**identity(), "native_sha256": hashlib.sha256(executable.read_bytes()).hexdigest()}


def page(rows, offset=0, *, limit=20, budget=18000):
    if type(offset) is not int or offset < 0:
        raise Invalid("Invalid library page.")
    result, size = [], 2
    for row in rows[offset:offset + limit]:
        count = len(json.dumps(row, ensure_ascii=True).encode()) + 2
        if size + count > budget:
            if not result:
                raise Invalid("One library entry exceeds the preview limit. Open its local diagnostics.")
            break
        result.append(row)
        size += count
    end = offset + len(result)
    return result, dict(offset=offset, total=len(rows), next=end if end < len(rows) else None)


def wire(state):
    raw = (json.dumps(state, ensure_ascii=True) + "\n").encode()
    if len(raw) > FRAME_BYTES:
        raise Invalid("Recorder state exceeds the 64 KiB connection limit; no action was dispatched.")
    return raw
