"""No desktop input: preserve hashes, challenge singleton, restart candidate only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from task_recorder.server import protect

root = Path(os.environ['LOCALAPPDATA']) / 'SportsCaveOS/TaskRecorderPhase1-20261022'
here = Path(__file__).resolve().parent
def hashes():
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ('tasks','desktop-v1') for p in (root/folder).rglob('*')
            if p.is_file() and 'runs' not in p.parts and p.name != 'draft.json'}
before = hashes()
exe = here/'desktop_recorder/bin/DesktopRecorder.exe'
other = subprocess.run([str(exe),'--candidate'], input=b'', capture_output=True,
                       timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
assert not other.stdout, 'Competing native runtime emitted commands'
cfg = json.loads((root/'connection.json').read_text())
key = protect(bytes.fromhex(cfg['protected']), True).decode()
with urlopen(Request(cfg['origin']+'/api/state', headers={'X-Recorder-Key':key})) as r:
    state = json.load(r)
assert state['mode'] == 'idle', 'Refuse restart of active candidate'
with urlopen(Request(cfg['origin']+'/api/shutdown', data=b'{}', headers={
    'X-Recorder-Key':key,'Content-Type':'application/json'}), timeout=15) as r:
    assert json.load(r)['stopping']
time.sleep(3)
logs = root/'restart.log'
with logs.open('ab') as output:
    child = subprocess.Popen([sys.executable,'-B',str(here/'run_local.py')],cwd=here,
        stdout=output,stderr=output,creationflags=subprocess.CREATE_NO_WINDOW)
deadline = time.monotonic()+20
while time.monotonic()<deadline:
    time.sleep(.3)
    try:
        current = json.loads((root/'connection.json').read_text())
        if current['protected']==cfg['protected']:continue
        new_key = protect(bytes.fromhex(current['protected']), True).decode()
        with urlopen(Request(current['origin']+'/api/state',headers={'X-Recorder-Key':new_key}),timeout=1) as r:
            after_state=json.load(r)
        break
    except OSError:continue
else:raise AssertionError('Candidate did not restart')
assert hashes()==before, 'Recording or revision changed during restart'
assert after_state['mode']=='idle', after_state['mode']
assert all(after_state['runtime'][k]==state['runtime'][k] for k in ('build','ipc','recording_format','action_versions'))
result=dict(recording_files_unchanged=len(before),singleton_rejected=True,
            restarted_idle=True,runtime=after_state['runtime'],pid=child.pid)
(root/'restart-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
