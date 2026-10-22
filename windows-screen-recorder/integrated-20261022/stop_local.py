"""Stop the isolated idle candidate without changing its recordings or pairing."""
import json, os
from pathlib import Path
from urllib.request import Request, urlopen
from task_recorder.server import protect
root=Path(os.environ['LOCALAPPDATA'])/'SportsCaveOS/TaskRecorderPhase1-20261022'
cfg=json.loads((root/'connection.json').read_text())
headers={'X-Recorder-Key':protect(bytes.fromhex(cfg['protected']),True).decode(),'Content-Type':'application/json'}
with urlopen(Request(cfg['origin']+'/api/state',headers=headers)) as r:
    assert json.load(r)['mode']=='idle', 'Candidate must be idle'
with urlopen(Request(cfg['origin']+'/api/shutdown',data=b'{}',headers=headers),timeout=15) as r:
    assert json.load(r)['stopping']
print('Isolated idle candidate stopped.')
