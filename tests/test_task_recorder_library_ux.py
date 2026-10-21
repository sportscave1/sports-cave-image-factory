"""Focused library/popup handoff checks; no Windows input or real helper data."""
import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest

desktop = pytest.importorskip('desktop_recorder.helper')
from desktop_recorder.contract import Invalid as DesktopInvalid
from task_recorder.device import DeviceAgent
from task_recorder.schema import Invalid


def target():
    return dict(app='synthetic.exe',window_key='Disposable example',control_type='Edit',
                automation_id='example',name='Example',scope=[])


def command(runner,kind,**payload):
    return runner.desktop.apply(dict(v=1,id=str(uuid4()),kind=kind,payload=payload))


def saved(runner):
    command(runner,'record',window=target())
    for value in ('one','two'):
        command(runner,'event',generation=runner.desktop.recording.generation,privacy='safe',
                action=dict(version=2,kind='set_text',requires=['uia.value.v2'],target=target(),value=value,timeout_ms=500))
    command(runner,'pause')
    assert runner.desktop.recording.state=='paused'
    command(runner,'resume')
    command(runner,'stop')
    name=runner.desktop.state()['suggested_name']
    assert name.startswith('Recording ') and len(name)<100
    command(runner,'save',name=name)
    return runner.desktop.last_saved


def test_stop_save_rename_reopen_and_delete_preserve_definition_and_revision(tmp_path):
    async def trial():
        runner=desktop.DesktopRunner(tmp_path)
        runner.open_toolbar=AsyncMock()
        runner.publish_native=AsyncMock()
        row=saved(runner)
        path=runner.desktop.repository.root/(row['id']+'.json')
        original=path.read_bytes()
        agent=DeviceAgent(runner,'http://127.0.0.1:18999',preview=True)
        try:
            result=await agent.perform('rename',dict(id=row['id'],name='Notes for tomorrow'),str(uuid4()))
            assert result['name']=='Notes for tomorrow'
            assert path.read_bytes()==original
            assert runner.desktop.repository.revision(runner.desktop.repository.get(row['id']))==row['revision']
            restarted=desktop.DesktopRunner(tmp_path)
            assert restarted.catalogue.summaries()[0]['name']=='Notes for tomorrow'
            await agent.perform('play',dict(id=row['id'],revision=row['revision']),str(uuid4()))
            assert runner.desktop.pending_play and runner.desktop.playback.run is None
            assert runner.desktop.state()['recording_name']=='Notes for tomorrow'
            with pytest.raises(Invalid,match='Stop and save'):
                await agent.perform('delete',dict(id=row['id']),str(uuid4()))
            command(runner,'play_stop',reason='Cancelled before input')
            assert not runner.busy(), (runner.desktop.pending_play, runner.desktop.playback.run, runner.desktop.recording.state, runner.job, runner.recording)
            await agent.perform('delete',dict(id=row['id']),str(uuid4()))
            assert path.read_bytes()==original
            assert desktop.DesktopRunner(tmp_path).catalogue.summaries()==[]
            with pytest.raises(DesktopInvalid,match='removed'):
                runner.desktop.repository.get(row['id'])
        finally:agent.db.close()
    asyncio.run(trial())


def test_popup_reopen_retains_recording_and_never_overwrites_playback_instruction(tmp_path):
    async def trial():
        runner=desktop.DesktopRunner(tmp_path)
        runner.open_toolbar=AsyncMock();runner.publish_native=AsyncMock()
        command(runner,'record',window=target())
        before=(runner.desktop.recording.task['id'],runner.desktop.recording.generation)
        agent=DeviceAgent(runner,'http://127.0.0.1:18999',preview=True)
        agent.operation_id=str(uuid4())
        operation=agent.operation_id
        await agent.perform('open-popup',{},str(uuid4()))
        assert agent.operation_id==operation
        agent.db.close()
        assert before==(runner.desktop.recording.task['id'],runner.desktop.recording.generation)
        assert runner.publish_native.call_args.args[0]['show_toolbar'] is True
        command(runner,'stop');command(runner,'save',name='Saved example')
        row=runner.desktop.last_saved
        # An empty draft is retained but honestly unavailable for playback.
        assert not runner.catalogue.summaries()[0]['playback_available']
        runner=desktop.DesktopRunner(tmp_path/'playing')
        runner.open_toolbar=AsyncMock();runner.publish_native=AsyncMock()
        row=saved(runner)
        await runner.desktop_command('play',row,str(uuid4()))
        assert runner.publish_native.call_args.args[0]['show_toolbar'] is True
        command(runner,'play_ready')
        instruction=dict(runner.desktop.native_instruction)
        await runner.desktop_command('open-popup',{},str(uuid4()))
        assert runner.desktop.native_instruction==instruction
        assert runner.desktop.playback.run['pending']==0
    asyncio.run(trial())


def test_play_pause_resume_stop_keeps_unconfirmed_effect_and_saved_bytes(tmp_path):
    async def trial():
        runner=desktop.DesktopRunner(tmp_path)
        runner.open_toolbar=AsyncMock();runner.publish_native=AsyncMock()
        row=saved(runner);path=runner.desktop.repository.root/(row['id']+'.json');before=path.read_bytes()
        await runner.desktop_command('play',row,str(uuid4()))
        command(runner,'play_ready')
        command(runner,'play_pause')
        command(runner,'play_result',step=0,verified=True)
        assert runner.desktop.playback.run['state']=='paused'
        command(runner,'play_resume')
        assert runner.desktop.playback.run['pending']==1
        command(runner,'play_stop',reason='User stopped playback')
        assert runner.desktop.playback.run['state']=='uncertain'
        assert runner.desktop.playback.run['pending']==1
        assert path.read_bytes()==before
        recovered=desktop.DesktopRunner(tmp_path)
        assert recovered.desktop.recovered_runs[-1]['pending']==1
        assert recovered.desktop.native_instruction is None
    asyncio.run(trial())
