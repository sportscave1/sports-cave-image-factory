"""Real Python-process exits on disposable data; NOT native Windows acceptance."""
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
import pytest
from test_phase2 import command, action
from desktop_recorder.coordinator import Coordinator
from desktop_recorder.contract import CAPABILITIES, Invalid
from desktop_recorder.playback import Playback


CHILD = r'''
import os, sys, json
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path.cwd()/'tests'))
from test_phase2 import command, action
from desktop_recorder.coordinator import Coordinator
from desktop_recorder.contract import CAPABILITIES
c=Coordinator(Path(sys.argv[1]))
c.apply(command('record', {'window': action()['target']}))
for _ in range(2): c.apply(command('event', dict(action=action(),privacy='safe',generation=c.recording.generation)))
c.apply(command('stop')); c.apply(command('save', {'name':'Disposable crash contract'}))
s=c.last_saved; p=c.playback
p.begin(str(uuid4()),s['id'],s['revision'],CAPABILITIES.values(),controls_visible=True,emergency_stop_ready=True)
mode=sys.argv[2]
if mode!='cold':
    p.dispatch(0)
    if mode=='paused_pending': p.pause()
    if mode=='stopped_pending': p.stop('Simulated helper loss')
    if mode in ('confirmed','paused_confirmed','cancelled_no_effect'):
        p.acknowledge(0,verified=mode!='cancelled_no_effect',no_effect=mode=='cancelled_no_effect')
    if mode=='paused_confirmed': p.pause()
os._exit(73)
'''


@pytest.mark.parametrize('mode,pending,next_step,state', [
    ('cold',None,0,'stopped'), ('pending',0,0,'uncertain'),
    ('paused_pending',0,0,'uncertain'), ('stopped_pending',0,0,'uncertain'),
    ('confirmed',None,1,'stopped'), ('paused_confirmed',None,1,'stopped'),
    ('cancelled_no_effect',None,0,'stopped')])
def test_abrupt_process_exit_preserves_exact_checkpoint(tmp_path, mode, pending, next_step, state):
    result = subprocess.run([sys.executable,'-X','utf8','-c',CHILD,str(tmp_path),mode],
                            capture_output=True,text=True,timeout=20)
    assert result.returncode == 73, result.stderr
    c = Coordinator(tmp_path)
    runs = c.playback.recover()
    assert len(runs) == 1
    run = runs[0]
    assert (run['pending'],run['next_step'],run['state']) == (pending,next_step,state)
    assert len(run['results']) == (1 if mode in ('confirmed','paused_confirmed','cancelled_no_effect') else 0)
    with pytest.raises(Invalid): c.playback.resume()
    with pytest.raises(Invalid): c.playback.dispatch(next_step)
    args=(str(uuid4()),run['task_id'],run['revision'],CAPABILITIES.values())
    if pending is not None:
        with pytest.raises(Invalid):
            c.playback.begin(*args,controls_visible=True,emergency_stop_ready=True)
        with pytest.raises(Invalid):
            c.playback.resume_recovered(run['id'],run['revision'],CAPABILITIES.values(),
                controls_visible=True,emergency_stop_ready=True)
    elif mode in ('confirmed','paused_confirmed'):
        resumed = c.playback.resume_recovered(run['id'],run['revision'],CAPABILITIES.values(),
            controls_visible=True,emergency_stop_ready=True)
        assert resumed['next_step'] == 1
        with pytest.raises(Invalid): c.playback.dispatch(0)
        c.playback.dispatch(1)
        c.playback.acknowledge(1,verified=True)
        assert c.playback.run['state'] == 'completed'
    elif mode in ('cold','cancelled_no_effect'):
        # Only these disposable no-effect runs are safe for a new explicit Play.
        c.playback.begin(*args,controls_visible=True,emergency_stop_ready=True)
        c.playback.stop()


@pytest.mark.parametrize('damage', ['revision','pending','prefix','total','cancelled','capabilities','controls','emergency','write_failure'])
def test_checkpoint_resume_refuses_unsafe_or_unpersisted_transition(tmp_path, damage, monkeypatch):
    result = subprocess.run([sys.executable,'-X','utf8','-c',CHILD,str(tmp_path),'paused_confirmed'],
                            capture_output=True,text=True,timeout=20)
    assert result.returncode == 73, result.stderr
    c=Coordinator(tmp_path); run=c.playback.recover()[0]
    path=c.playback.root/(run['id']+'.json')
    if damage=='pending': run['pending']=1
    if damage=='prefix': run['results']=[]
    if damage=='total': run['total']=99
    if damage=='cancelled': run['stop_reason']='Explicit cancellation'
    c.repository.atomic(path,run)
    before=path.read_bytes()
    if damage=='write_failure':
        def fail(*args): raise OSError('disk unavailable')
        monkeypatch.setattr(c.repository,'atomic',fail)
    with pytest.raises((Invalid,OSError)):
        c.playback.resume_recovered(run['id'],'0'*64 if damage=='revision' else run['revision'],
            [] if damage=='capabilities' else CAPABILITIES.values(),
            controls_visible=damage!='controls',emergency_stop_ready=damage!='emergency')
    assert path.read_bytes()==before
    with pytest.raises(Invalid): c.playback.dispatch(1)
