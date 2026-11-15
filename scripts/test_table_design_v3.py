"""Own loopback-only before/after fixture servers and browser regression tests."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    scratch = ROOT / 'tmp/table-v3-temp'
    scratch.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'TEMP': str(scratch), 'TMP': str(scratch),
           'STREAMLIT_BROWSER_GATHER_USAGE_STATS': 'false'}
    processes = []
    logs = []
    phases = ['before', 'after'] if (ROOT / 'tmp/table-v3-baseline/app.py').exists() else ['after']
    env['TABLE_V3_PHASES'] = ','.join(phases)
    try:
        for phase in [*phases, 'orders']:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            env['TABLE_V3_' + phase.upper() + '_URL'] = f'http://127.0.0.1:{port}'
            log = (scratch / (phase + '.log')).open('w', encoding='utf8')
            logs.append(log)
            fixture = 'orders_compact' if phase == 'orders' else 'table_v3_preview'
            command = [sys.executable, '-m', 'streamlit', 'run', f'tests/fixtures/{fixture}.py',
                       '--server.address', '127.0.0.1', '--server.port', str(port),
                       '--server.headless', 'true']
            if phase == 'before':
                # Streamlit's original default table palette (no custom theme).
                command += ['--theme.dataframeBorderColor', '#e6e9ef',
                            '--theme.dataframeHeaderBackgroundColor', '#f0f2f6']
            process = subprocess.Popen(command, cwd=ROOT, env={**env, 'TABLE_V3_PHASE': phase},
                                       stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            processes.append(process)
            deadline = time.monotonic() + 40
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f'{phase} fixture exited; see {log.name}')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health', timeout=1):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        raise RuntimeError(f'{phase} fixture startup timed out')
                    time.sleep(.2)
        result = subprocess.run(['node', 'tests/test_table_design_v3_ui.cjs'], cwd=ROOT, env=env, timeout=500)
        return result.returncode
    finally:
        for process in processes:
            if os.name == 'nt' and process.poll() is None:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        for log in logs:
            log.close()


if __name__ == '__main__':
    sys.exit(main())
