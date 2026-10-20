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
            await agent.perform("play", saved, str(uuid4()))
            assert runner.desktop.native_instruction["kind"] == "arm"
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
