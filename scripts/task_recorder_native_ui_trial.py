"""Isolated native helper for real panel/relay acceptance, never installation.

Only explicitly imported synthetic desktop definitions are available. The paired
website must be a loopback preview. No browser input is synthesized by this file.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--import-task', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18933)
    parser.add_argument('--serve', action='store_true')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    root = args.root.resolve()
    installed = Path(os.environ['LOCALAPPDATA']) / 'SportsCaveOS'
    if root == repo or repo in root.parents or root == installed or installed in root.parents:
        raise SystemExit('Synthetic helper storage must be outside source and installed helper data.')
    if not args.serve:
        allowed = {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'USERPROFILE',
                   'APPDATA', 'LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'TEMP', 'TMP'}
        env = {k:v for k,v in os.environ.items() if k.upper() in allowed}
        env.update(PYTHONDONTWRITEBYTECODE='1', SPORTS_CAVE_RECORDER_SOURCE=str(repo),
                   PYTHONPATH=os.pathsep.join([str(repo / 'windows-screen-recorder'), str(repo)]))
        return subprocess.call([sys.executable, '-B', str(Path(__file__).resolve()),
            '--serve', '--root', str(root), '--import-task', str(args.import_task.resolve()),
            '--port', str(args.port)], cwd=repo, env=env)
    if root.exists() and any(root.iterdir()) and not (root / 'synthetic-trial.json').is_file():
        raise SystemExit('Refusing existing storage without a synthetic trial marker.')
    root.mkdir(parents=True, exist_ok=True)
    from desktop_recorder.contract import validate
    from desktop_recorder.helper import native_path
    from desktop_recorder.integration import Repository
    from task_recorder.server import Bridge, instance_lock, protect
    from task_recorder.store import atomic, Store
    task = validate(json.loads(args.import_task.read_text(encoding='utf-8')))
    # This acceptance launcher deliberately accepts only the known disposable trial.
    if (task['name'] != 'Combined 21' or len(task['actions']) != 4 or
        [a['kind'] for a in task['actions']] != ['focus_window','set_text','focus_window','set_text'] or
        task['actions'][1]['value'] != 'Edge combined 21' or
        task['actions'][3]['value'] != 'Notepad combined 21'):
        raise SystemExit('Import the reviewed Combined 21 synthetic recording.')
    atomic(root / 'synthetic-trial.json', {'task_id':task['id'], 'purpose':'native UI relay acceptance'})
    Repository(root, atomic, Store.revision).save(task)
    connect = socket.socket.connect
    def local_connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {'127.0.0.1','localhost','::1'}:
            raise RuntimeError('Synthetic helper network is loopback-only.')
        return connect(sock, address)
    socket.socket.connect = local_connect
    binary = native_path().resolve()
    def audit(event, items):
        if event == 'subprocess.Popen':
            executable, arguments = items[:2]
            expected = [str(binary), '--candidate']
            # Windows can supply executable=None and an already-quoted command
            # line to this event. Validate that exact command without launching
            # a shell or accepting extra flags.
            if ((executable is not None and Path(executable).resolve() != binary) or
                (arguments != expected and arguments != subprocess.list2cmdline(expected))):
                raise RuntimeError('Only the reviewed native recorder may run during this trial.')
        if event in {'os.system','os.posix_spawn','os.fork'}:
            raise RuntimeError('Background jobs are disabled during this trial.')
    sys.addaudithook(audit)
    with instance_lock(root / 'recorder.lock'):
        server = Bridge(root, args.port, preview=True)
        if type(server.runner).__name__ != 'DesktopRunner':
            server.close()
            raise SystemExit('The native desktop adapter is unavailable.')
        original_perform = server.agent.perform
        async def traced_perform(kind, data, command_id):
            try:
                return await original_perform(kind, data, command_id)
            except Exception as error:
                import traceback
                atomic(root / 'trial-control-error.json', {
                    'kind':kind, 'error_type':type(error).__name__,
                    'message':str(error)[:240],
                    'stack':[{'file':Path(frame.filename).name,'line':frame.lineno,'function':frame.name}
                             for frame in traceback.extract_tb(error.__traceback__)]})
                raise
        server.agent.perform = traced_perform
        atomic(root / 'connection.json', {'origin':server.origin, 'protected':protect(server.token.encode()).hex()})
        previous = server.runner.state_changed
        def project():
            previous()
            atomic(root / 'trial-state.json', server.agent.snapshot())
        server.runner.state_changed = project
        project()
        atomic(root / 'trial-process.json', {'pid':os.getpid(), 'origin':server.origin})
        print('Synthetic native helper ready at ' + server.origin, flush=True)
        try:
            server.serve_forever(poll_interval=.2)
        finally:
            server.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
