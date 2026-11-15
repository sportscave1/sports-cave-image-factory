"""Mandatory offline pre-deploy gate for shared-runtime changes; no credentials."""
from pathlib import Path
import subprocess
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    modules = sorted({f'tests.{path.stem}' for pattern in ('test_support_email*.py', 'test_email*.py')
                      for path in (ROOT / 'tests').glob(pattern)})
    result = subprocess.call([sys.executable, '-m', 'unittest', *modules], cwd=ROOT)
    if result:
        return result
    node = shutil.which('node')
    if not node:
        print('FAIL: Node.js is required for the Email component regression gate.')
        return 1
    components = sorted({str(path.relative_to(ROOT)) for pattern in ('test_email*.cjs', 'test_support_email*.cjs')
                         for path in (ROOT / 'tests').glob(pattern)})
    return subprocess.call([node, '--test', *components], cwd=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
