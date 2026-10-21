"""Run with the reviewed desktop package on PYTHONPATH; no native input."""
import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock
import pytest

desktop = pytest.importorskip("desktop_recorder.helper")
from task_recorder.device import DeviceAgent
from desktop_recorder.contract import FORMAT


def definition():
    return {"format":FORMAT, "version":1, "id":str(uuid4()), "name":"Synthetic desktop",
            "starting_context":{"mode":"prepared","binding":None}, "actions":[{
                "version":2,"kind":"set_text","requires":["uia.value.v2"],
                "target":{"app":"synthetic.exe","window_key":"Synthetic document",
                          "control_type":"Edit","automation_id":"input","name":"Example","scope":[]},
                "value":"Synthetic value","timeout_ms":500}]}


def test_shutdown_of_interrupted_capture_does_not_reopen_toolbar_even_if_pipe_is_broken(tmp_path):
    async def trial():
        from types import SimpleNamespace
        from unittest.mock import Mock
        runner=desktop.DesktopRunner(tmp_path)
        runner.desktop.recording.record({'mode':'prepared','binding':None},indicator_visible=True)
        runner.desktop.recording.interrupt('synthetic interruption')
        reader=asyncio.StreamReader()
        process=SimpleNamespace(stdout=reader,returncode=None,
                                stdin=SimpleNamespace(close=Mock(),wait_closed=AsyncMock()))
        def terminate():
            process.returncode=0
            reader.feed_eof()
        process.terminate=Mock(side_effect=terminate)
        process.wait=AsyncMock(return_value=0)
        runner.native=process
        runner.native_pump=asyncio.create_task(runner.read_native(process))
        runner.open_toolbar=AsyncMock(side_effect=AssertionError('Shutdown reopened toolbar'))
        runner.publish_native=AsyncMock(side_effect=BrokenPipeError())
        await runner.close()
        process.terminate.assert_called_once()
        process.stdin.close.assert_called_once()
        assert runner.native_pump.done()
        runner.open_toolbar.assert_not_called()
        recovered=desktop.DesktopRunner(tmp_path)
        assert recovered.desktop.recording.state=='interrupted'
        assert recovered.desktop.recording.task['actions']==[]
    asyncio.run(trial())


def test_old_native_reader_cannot_stop_replacement_or_consume_its_frames(tmp_path):
    async def trial():
        from types import SimpleNamespace
        old_reader=asyncio.StreamReader();old_reader.feed_eof()
        old=SimpleNamespace(stdout=old_reader)
        replacement=SimpleNamespace(stdout=SimpleNamespace(readline=AsyncMock()))
        runner=desktop.DesktopRunner(tmp_path)
        runner.native=replacement
        runner.desktop.pending_play={'synthetic':'replacement awaiting local confirmation'}
        runner.desktop.message='Replacement ready'
        await runner.read_native(old)
        assert runner.desktop.pending_play is not None
        assert runner.desktop.message=='Replacement ready'
        replacement.stdout.readline.assert_not_awaited()
    asyncio.run(trial())


def test_catalogue_and_capabilities_reuse_helper_snapshot(tmp_path):
    runner = desktop.DesktopRunner(tmp_path)
    task = definition()
    saved = runner.desktop.repository.save(task)
    agent = DeviceAgent(runner, "http://127.0.0.1:18990", preview=True)
    try:
        snapshot = agent.snapshot()
        row = next(r for r in snapshot["tasks"] if r["id"] == saved["id"])
        assert row["playback_available"] is True
        assert snapshot["desktop_capabilities"]["action_versions"] == [2]
        assert snapshot["protocol"] == 4  # Numeric browser protocol is not desktop support.
    finally:
        agent.db.close()


def test_relay_dispatch_routes_desktop_without_opening_browser(tmp_path):
    async def trial():
        runner = desktop.DesktopRunner(tmp_path)
        saved = runner.desktop.repository.save(definition())
        runner.open_toolbar = AsyncMock()
        runner.publish_native = AsyncMock()
        runner.open_browser = AsyncMock(side_effect=AssertionError("replacement browser"))
        agent = DeviceAgent(runner, "http://127.0.0.1:18990", preview=True)
        try:
            detail = await agent.perform("inspect", {"id":saved["id"]}, str(uuid4()))
            assert detail["desktop"] is True
            runner.open_toolbar.assert_not_called()
            await agent.perform("play", saved, str(uuid4()))
            assert runner.desktop.native_instruction["kind"] == "arm"
            assert agent.snapshot()["mode"] == "starting"
            assert runner.desktop.playback.run is None  # Wait for real native Stop registration.
            runner.open_browser.assert_not_called()
        finally:
            agent.db.close()
    asyncio.run(trial())


def test_rejected_native_command_is_acknowledged_and_next_command_works(tmp_path):
    async def trial():
        runner = desktop.DesktopRunner(tmp_path)
        runner.publish_native = AsyncMock()
        bad = dict(v=1, id=str(uuid4()), kind="resume", payload={})
        await runner.apply_native(bad)
        response = runner.publish_native.call_args.args[0]
        assert response["ack"] == bad["id"]
        assert response["state"] == "idle"
        good = dict(v=1, id=str(uuid4()), kind="diagnostic", payload={"kind":"test"})
        await runner.apply_native(good)
        assert runner.publish_native.call_args.args[0]["ack"] == good["id"]
        assert runner.desktop.diagnostics == [{"kind":"test"}]
    asyncio.run(trial())


def test_cancel_before_local_play_confirmation_never_dispatches_or_repeats(tmp_path):
    async def trial():
        runner = desktop.DesktopRunner(tmp_path)
        runner.open_toolbar = AsyncMock()
        runner.publish_native = AsyncMock()
        saved = runner.desktop.repository.save(definition())
        play_id = str(uuid4())
        await runner.desktop_command("play", saved, play_id)
        assert runner.desktop.native_instruction["require_local_confirmation"] is True
        assert runner.state()["mode"] == "starting"
        assert "Start playback" in runner.state()["message"]
        assert runner.desktop.playback.run is None
        await runner.desktop_command("stop", {}, str(uuid4()))
        assert runner.desktop.pending_play is None
        assert runner.desktop.native_instruction["kind"] == "disarm"
        await runner.desktop_command("play", saved, play_id)  # Durable duplicate, not a new request.
        assert runner.desktop.pending_play is None
        with pytest.raises(ValueError, match="No pending Play"):
            runner.desktop.apply(dict(v=1, id=str(uuid4()), kind="play_ready", payload={}))
        assert runner.desktop.playback.run is None
    asyncio.run(trial())


def test_toolbar_cannot_start_during_browser_job(tmp_path):
    async def trial():
        runner = desktop.DesktopRunner(tmp_path)
        runner.publish_native = AsyncMock()
        runner.job = asyncio.get_running_loop().create_future()
        command = dict(v=1, id=str(uuid4()), kind="record",
                       payload={"window":definition()["actions"][0]["target"]})
        await runner.apply_native(command)
        response = runner.publish_native.call_args.args[0]
        assert response["ack"] == command["id"]
        assert "browser session" in response["message"]
        assert runner.desktop.recording.state == "idle"
        assert runner.desktop.recording.task is None
        runner.job.cancel()
    asyncio.run(trial())


def test_relay_receipt_waits_for_correlated_native_flush_and_is_durable(tmp_path):
    async def trial():
        runner = desktop.DesktopRunner(tmp_path)
        runner.open_toolbar = AsyncMock()
        runner.publish_native = AsyncMock()
        runner.desktop.apply(dict(v=1, id=str(uuid4()), kind="record",
                                 payload={"window":definition()["actions"][0]["target"]}))
        agent = DeviceAgent(runner, "http://127.0.0.1:18990", preview=True)
        key = str(uuid4())
        command = dict(id=key, kind="pause", payload={}, valid_for=10,
                       boot_id=agent.boot_id, fence=0)
        try:
            snapshot = agent.snapshot()
            assert snapshot["selected_id"] == runner.desktop.recording.task["id"]
            assert next(t for t in snapshot["tasks"] if t["id"] == snapshot["selected_id"])["playback_available"] is False
            pending = asyncio.create_task(agent.apply(command))
            await asyncio.sleep(0)
            assert not pending.done()
            assert agent.db.execute("SELECT status FROM commands WHERE id=?", (key,)).fetchone()[0] == "accepted"
            assert runner.desktop.native_instruction["request_id"] == key
            await runner.apply_native(dict(v=1, id=str(uuid4()), kind="diagnostic",
                                           payload={"request_id":key, "kind":"unrelated"}))
            assert not pending.done()
            await runner.apply_native(dict(v=1, id=str(uuid4()), kind="pause", payload={"request_id":key}))
            await pending
            assert runner.desktop.recording.state == "paused"
            assert agent.acks[key]["status"] == "applied"
            before = runner.publish_native.call_count
            await agent.apply(command)
            assert runner.publish_native.call_count == before  # No repeated flush on duplicate delivery.
            assert agent.db.execute("SELECT status FROM commands WHERE id=?", (key,)).fetchone()[0] == "applied"
        finally:
            agent.db.close()
    asyncio.run(trial())


def test_disconnect_rejects_unconfirmed_stop_receipt_and_preserves_draft(tmp_path):
    async def trial():
        from types import SimpleNamespace
        runner = desktop.DesktopRunner(tmp_path)
        runner.open_toolbar = AsyncMock()
        runner.publish_native = AsyncMock()
        runner.desktop.apply(dict(v=1, id=str(uuid4()), kind="record",
                                 payload={"window":definition()["actions"][0]["target"]}))
        original = runner.desktop.recording.task["id"]
        agent = DeviceAgent(runner, "http://127.0.0.1:18990", preview=True)
        key = str(uuid4())
        try:
            pending = asyncio.create_task(agent.apply(dict(id=key, kind="stop", payload={},
                valid_for=10, boot_id=agent.boot_id, fence=0)))
            await asyncio.sleep(0)
            assert not pending.done()
            reader = asyncio.StreamReader()
            reader.feed_eof()
            runner.native = SimpleNamespace(stdout=reader)
            await runner.read_native()
            await pending
            assert agent.acks[key]["status"] == "uncertain"
            assert runner.desktop.recording.state == "interrupted"
            assert runner.desktop.recording.task["id"] == original
            assert not runner.capture_waiters
            recovered = desktop.DesktopRunner(tmp_path)
            assert recovered.desktop.recording.task["id"] == original
            assert recovered.desktop.recording.state == "interrupted"
            assert agent.db.execute("SELECT status FROM commands WHERE id=?", (key,)).fetchone()[0] == "uncertain"
        finally:
            agent.db.close()
    asyncio.run(trial())


def test_disconnect_during_dispatched_action_is_interrupted_and_never_replayed(tmp_path):
    async def trial():
        import json
        from types import SimpleNamespace
        from desktop_recorder.contract import Invalid
        runner = desktop.DesktopRunner(tmp_path)
        saved = runner.desktop.repository.save(definition())
        path = runner.desktop.repository.root / (saved['id'] + '.json')
        before = path.read_bytes()
        runner.last_engine = 'desktop'
        playback = runner.desktop.playback
        playback.begin(str(uuid4()), saved['id'], saved['revision'], {'uia.value.v2'},
                       controls_visible=True, emergency_stop_ready=True)
        playback.dispatch(0)
        reader = asyncio.StreamReader()
        reader.feed_eof()
        runner.native = SimpleNamespace(stdout=reader)
        await runner.read_native()
        state = runner.state()
        assert state['mode'] == 'interrupted'
        assert 'disconnected' in state['message']
        journal = json.loads((playback.root / (playback.run['id'] + '.json')).read_text(encoding='utf-8'))
        assert journal['state'] == 'uncertain' and journal['pending'] == 0
        assert journal['result_received'] is False and journal['results'] == []
        recovered = desktop.DesktopRunner(tmp_path)
        assert recovered.desktop.native_instruction is None
        assert recovered.desktop.recovered_runs[-1]['pending'] == 0
        assert path.read_bytes() == before
        with pytest.raises(Invalid, match='uncertain previous action'):
            recovered.desktop.playback.begin(str(uuid4()), saved['id'], saved['revision'], {'uia.value.v2'},
                                            controls_visible=True, emergency_stop_ready=True)
    asyncio.run(trial())
