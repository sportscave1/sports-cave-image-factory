"""Optional native adapter for the existing authenticated helper.

Uses DeviceAgent's relay and command receipts. No new listener or account store.
All coordinator mutations run on the helper asyncio loop.
"""
import asyncio
import contextlib
import json
from pathlib import Path
from uuid import uuid4

from task_recorder.runner import Runner
from task_recorder.schema import Invalid
from .coordinator import Coordinator
from .catalogue import Catalogue
from .contract import CAPABILITIES, FORMAT


def native_path():
    package = Path(__file__).resolve().parent
    installed = package / "bin" / "DesktopRecorder.exe"
    return installed if installed.exists() else package.parent / "native" / "bin" / "DesktopRecorder.exe"


class DesktopRunner(Runner):
    def __init__(self, root, **kwargs):
        super().__init__(root, **kwargs)
        self.desktop = Coordinator(root)
        self.catalogue = Catalogue(self.desktop.repository, self.store, playback_available=True)
        self.native = None
        self.native_pump = None
        self.native_lock = asyncio.Lock()
        self.last_engine = None
        self.capture_waiters = {}
        self.message = "Windows recorder ready. Choose Record to select a prepared window."

    def desktop_busy(self):
        return self.desktop.recording.state != "idle" or self.desktop.pending_play is not None or (
            self.desktop.playback.run and self.desktop.playback.run["state"] in {"playing", "paused", "uncertain"})

    def busy(self):
        return super().busy() or bool(getattr(self, "desktop", None) and self.desktop_busy())

    def state(self):
        state = super().state()
        if not hasattr(self, "desktop"):
            return state
        state["tasks"] = self.catalogue.summaries()
        state["desktop_capabilities"] = {
            "format": FORMAT, "version": 1, "action_versions": [2],
            "capture": True, "playback": True,
            "actions": [c.replace(".v1", ".v2") for c in CAPABILITIES.values()],
        }
        r = self.desktop.recording
        run = self.desktop.playback.run
        if r.state != "idle":
            state["tasks"].append(dict(id=r.task["id"], name=r.task["name"], format=FORMAT,
                format_version=1, playback_available=False, inputs=[], steps=len(r.task["actions"]),
                revision=None, duration_ms=r.elapsed_ms, updated_at=None, result="Unsaved desktop recording"))
            state.update(mode={"recording":"recording", "paused":"recording_paused",
                               "draft":"interrupted", "interrupted":"interrupted"}[r.state],
                         recording=r.state == "recording", message=r.problem or self.desktop.message,
                         active_task_id=r.task["id"], active_task_name=r.task["name"], selected_id=r.task["id"],
                         step=len(r.task["actions"]), total=len(r.task["actions"]))
        elif self.desktop.pending_play:
            selected = next(t for t in state["tasks"] if t["id"] == self.desktop.pending_play["task_id"])
            state.update(mode="starting", message=self.desktop.message,
                         active_task_id=selected["id"], active_task_name=selected["name"],
                         total=selected["steps"], selected_id=selected["id"])
        elif run and self.last_engine == "desktop":
            mode = {"playing":"running", "paused":"paused", "uncertain":"running",
                    "stopped":"stopped", "completed":"completed"}[run["state"]]
            if run["state"] == "uncertain" and run.get("message"):
                mode = "interrupted"
            state.update(mode=mode, message=self.desktop.message, step=run["next_step"],
                         total=run["total"], active_task_id=run["task_id"],
                         active_task_name=next((t["name"] for t in state["tasks"] if t["id"] == run["task_id"]), "Desktop recording"),
                         selected_id=run["task_id"],
                         can_resume=run["pause_requested"])
        elif self.last_engine == "desktop":
            state["message"] = self.desktop.message
        # Results are projections of durable run journals, never saved-definition edits.
        for history in [*self.desktop.recovered_runs, *([run] if run else [])]:
            for row in state["tasks"]:
                if row["id"] == history["task_id"] and row.get("revision") == history["revision"]:
                    row["result"] = {"uncertain":"interrupted", "playing":"running"}.get(history["state"], history["state"])
        return state

    async def publish_native(self, state=None):
        if self.native and self.native.returncode is None:
            wire = (json.dumps(state or self.desktop.state()) + "\n").encode()
            if len(wire) > 65536:
                raise Invalid("Native state exceeded its connection bound.")
            self.native.stdin.write(wire)
            await asyncio.wait_for(self.native.stdin.drain(), timeout=3)
        self.notify_state()

    async def apply_native(self, command):
        try:
            if command.get("kind") in {"record", "play"} and (super().busy() or self.recording):
                raise Invalid("Stop the browser session before starting a desktop session.")
            state = self.desktop.apply(command)
            if command.get("kind") in {"record", "play"}:
                self.last_engine = "desktop"
        except Exception as error:
            if self.desktop.recording.state in {"recording", "paused"}:
                try:
                    self.desktop.recording.interrupt("Native command failed; draft preserved.")
                except OSError:
                    self.desktop.recording.problem = "Disk write failed. Draft retained in memory."
            self.desktop.message = str(error)[:240]
            state = self.desktop.state()
            state["ack"] = command.get("id")
            waiter = self.capture_waiters.get(command.get("payload", {}).get("request_id"))
            if waiter and not waiter[1].done():
                waiter[1].set_exception(Invalid(self.desktop.message))
        else:
            waiter = self.capture_waiters.get(command.get("payload", {}).get("request_id"))
            if waiter and command.get("kind") == waiter[0] and not waiter[1].done():
                waiter[1].set_result(None)
        await self.publish_native(state)

    async def open_toolbar(self):
        if self.native and self.native.returncode is None:
            return
        executable = native_path()
        if not executable.is_file():
            raise Invalid("Update required: native recorder package is missing.")
        # No injected-input acceptance flag is reachable from this entry point.
        self.native = await asyncio.create_subprocess_exec(
            str(executable), "--candidate", stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            limit=65538)
        self.native_pump = asyncio.create_task(self.read_native())
        await self.publish_native()

    async def read_native(self):
        try:
            while True:
                line = await self.native.stdout.readline()
                if not line:
                    break
                if len(line) > 65536 or not line.endswith(b"\n"):
                    raise Invalid("Native connection frame exceeded its bound.")
                async with self.native_lock:
                    command = json.loads(line)
                    if not isinstance(command, dict):
                        raise Invalid("Native command must be an object.")
                    await self.apply_native(command)
        except Exception as error:
            self.desktop.message = "Native connection interrupted: " + type(error).__name__
        finally:
            self.desktop.message = "Native toolbar disconnected. Review the preserved recording or run before continuing."
            self.desktop.pending_play = None
            self.desktop.playback.stop(reason=self.desktop.message)
            if self.desktop.recording.state in {"recording", "paused"}:
                try:
                    self.desktop.recording.interrupt("Native toolbar disconnected. Review the draft.")
                except OSError:
                    self.desktop.recording.problem = "Disk write failed. Draft retained in memory; review after restoring disk access."
            for _, future in self.capture_waiters.values():
                if not future.done():
                    future.set_exception(ConnectionError("Native toolbar disconnected before capture confirmation."))
            self.notify_state()

    async def desktop_command(self, kind, data, command_id):
        if kind != "inspect":
            self.last_engine = "desktop"
        if kind == "inspect":
            task = self.desktop.repository.get(data["id"])
            return {"task":task, "revision":self.store.revision(task), "values":{},
                    "desktop":True, "playback_available":True}
        await self.open_toolbar()
        if kind == "record":
            if self.busy() or self.recording:
                raise Invalid("Stop the current session first.")
            self.desktop.message = "Choose your prepared window and press Record on the Windows toolbar."
            await self.publish_native()
            return {"message":self.desktop.message}
        if kind in {"pause", "resume", "stop"}:
            if self.desktop.recording.state in {"recording", "paused"}:
                if kind == "resume":
                    native_kind = "resume"
                else:
                    # Native flush barrier must acknowledge before changing state.
                    future = asyncio.get_running_loop().create_future()
                    self.capture_waiters[command_id] = (kind, future)
                    try:
                        self.desktop.instruct("capture_" + kind, request_id=command_id)
                        await self.publish_native()
                        await asyncio.wait_for(future, timeout=4)
                    except (asyncio.TimeoutError, ConnectionError, asyncio.CancelledError):
                        if self.desktop.recording.state in {"recording", "paused"}:
                            self.desktop.recording.interrupt("Native capture confirmation was lost. Review the preserved draft.")
                        self.notify_state()
                        raise
                    finally:
                        self.capture_waiters.pop(command_id, None)
                    return {"message":self.desktop.message}
            else:
                native_kind = "play_" + kind
        else:
            native_kind = kind
        if kind == "play":
            data = {**data, "confirm_on_toolbar":True}
        async with self.native_lock:
            self.desktop.apply(dict(v=1, id=command_id, kind=native_kind, payload=data))
            await self.publish_native()
        return {"message":self.desktop.message}

    def is_desktop(self, task_id):
        return any(t["id"] == task_id and t.get("format") == FORMAT for t in self.catalogue.summaries())

    async def stop(self):
        if self.desktop_busy():
            await self.desktop_command("stop", {}, str(uuid4()))
        else:
            await super().stop()

    async def close(self):
        self.desktop.playback.stop()
        if self.native and self.native.returncode is None:
            self.desktop.instruct("disarm")
            with contextlib.suppress(Exception):
                await self.publish_native()
            self.native.terminate()
            await self.native.wait()
        if self.native_pump:
            with contextlib.suppress(asyncio.CancelledError):
                await self.native_pump
        await super().close()
