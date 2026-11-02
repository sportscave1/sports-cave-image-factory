"""Real coordinator with a simulated native flush; no desktop input or network."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from desktop_recorder.coordinator import Coordinator
from desktop_recorder.helper import DesktopRunner
from task_recorder.device import DeviceAgent
from test_foundation import action
from test_phase2 import command


class ConnectionInterruptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.r = DesktopRunner.__new__(DesktopRunner)
        self.r.desktop = Coordinator(self.root)
        self.r.recording, self.r.mode = False, "idle"
        self.r.capture_waiters = {}
        self.r.notify_state = lambda: None
        self.r.open_toolbar = AsyncMock()
        self.r.publish_native = AsyncMock(side_effect=self.flush)
        self.r.native_lock = asyncio.Lock()
        self.r.closing = False
        self.patch = patch("task_recorder.runner.Runner.busy", return_value=False)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    async def flush(self, state=None):
        instruction = self.r.desktop.native_instruction
        if instruction and instruction["kind"] == "capture_stop":
            # The actual pipe emits Stop only after all pending input is flushed.
            self.r.desktop.apply(command("stop"))
            self.r.capture_waiters[instruction["request_id"]][1].set_result(None)

    def start(self):
        self.r.desktop.apply(command("record", {"mode": "desktop_session"}))
        self.r.desktop.apply(command("event", dict(action=action(), privacy="safe",
            generation=self.r.desktop.recording.generation)))

    async def test_loss_flushes_once_and_preserves_interruption_on_retries(self):
        self.start()
        await self.r.connection_lost()
        r = self.r.desktop.recording
        self.assertEqual(r.state, "interrupted")
        self.assertEqual(len(r.task["actions"]), 1)
        self.assertIn("OS connection lost", r.problem)
        generation, calls = r.generation, self.r.publish_native.await_count
        await self.r.connection_lost()
        self.assertEqual(r.generation, generation)
        self.assertEqual(self.r.publish_native.await_count, calls)
        self.assertEqual(self.r.desktop.native_instruction["kind"], "disarm")
        self.assertEqual(len(self.r.desktop.repository.load_draft()["task"]["actions"]), 1)

    async def test_stopped_draft_is_not_stopped_again_or_relabelled(self):
        self.start()
        self.r.desktop.apply(command("stop"))
        before = self.r.desktop.state()
        await self.r.connection_lost()
        self.assertEqual(self.r.desktop.state(), before)
        self.r.publish_native.assert_not_awaited()

    async def test_paused_capture_is_preserved_and_revocation_explained(self):
        self.start()
        self.r.desktop.apply(command("pause"))
        await self.r.connection_lost(revoked=True)
        self.assertEqual(self.r.desktop.recording.state, "interrupted")
        self.assertIn("PC was disconnected", self.r.desktop.recording.problem)

    async def test_flush_timeout_remains_interrupted_and_never_retries(self):
        self.start()
        self.r.desktop_command = AsyncMock(side_effect=asyncio.TimeoutError)
        await self.r.connection_lost()
        await self.r.connection_lost()
        self.r.desktop_command.assert_awaited_once()
        self.assertEqual(self.r.desktop.recording.state, "interrupted")

    async def test_pending_start_is_disarmed_without_dispatch(self):
        self.r.desktop.pending_play = {"task_id": str(uuid4())}
        await self.r.connection_lost()
        self.assertIsNone(self.r.desktop.pending_play)
        self.assertIsNone(self.r.desktop.playback.run)
        self.assertEqual(self.r.desktop.native_instruction["kind"], "disarm")

    async def test_device_disconnect_uses_desktop_hook_not_generic_stop(self):
        runner = SimpleNamespace(busy=lambda: True, recording=False, mode="idle",
            connection_lost=AsyncMock(), stop=AsyncMock(), message="")
        agent = DeviceAgent.__new__(DeviceAgent)
        agent.runner, agent.active_commands, agent.preparing = runner, {}, False
        await agent.network_lost()
        runner.connection_lost.assert_awaited_once_with(revoked=False)
        runner.stop.assert_not_awaited()

    async def test_os_stop_provenance_is_distinct_and_payload_free(self):
        self.start()
        await self.r.stop_from_device()
        rows = json.loads((self.root / "control-provenance.json").read_text())
        self.assertEqual(rows[-1]["source"], "os")
        self.assertEqual(rows[-1]["kind"], "stop")
        self.assertEqual(set(rows[-1]), {"at", "source", "kind", "recording", "playback", "pending_play", "command_id"})
        self.assertEqual(self.r.desktop.recording.state, "draft")

    def test_control_trace_is_bounded_and_does_not_log_events(self):
        for _ in range(105):
            self.r.control_trace("native", "stop", str(uuid4()))
        self.r.control_trace("native", "event", "private value must not be logged")
        rows = json.loads((self.root / "control-provenance.json").read_text())
        self.assertEqual(len(rows), 100)
