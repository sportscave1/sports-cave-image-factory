"""Optional native adapter for the existing authenticated helper.

Uses DeviceAgent's relay and command receipts. No new listener or account store.
All coordinator mutations run on the helper asyncio loop.
"""
import asyncio
import contextlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from task_recorder.runner import Runner
from task_recorder.schema import Invalid
from .coordinator import Coordinator, playback_capabilities
from .catalogue import Catalogue
from .contract import CAPABILITIES, FORMAT
from .session_protocol import identity, verify_package, wire, page


def native_path():
    package = Path(__file__).resolve().parent
    installed = package / "bin" / "DesktopRecorder.exe"
    return installed if installed.exists() else package.parent / "native" / "bin" / "DesktopRecorder.exe"


def native_arguments(root, development_test_input=False):
    args = ["--candidate"]
    if development_test_input:
        isolated = Path(os.environ['LOCALAPPDATA']) / 'SportsCaveOS/TaskRecorderPhase1-20261022'
        if Path(root).resolve() != isolated.resolve():
            raise Invalid('Injected test input is limited to the isolated development candidate.')
        args.append('--accept-injected-test-input')
    return args


class DesktopRunner(Runner):
    def __init__(self, root, **kwargs):
        super().__init__(root, **kwargs)
        self.desktop = Coordinator(root)
        self.catalogue = Catalogue(self.desktop.repository, self.store, playback_available=True)
        self.native = None
        self.native_pump = None
        self.native_ready = None
        self.native_lock = asyncio.Lock()
        self.last_engine = "desktop" if self.desktop.recovered_runs else None
        self.deadline_watch = None
        self.capture_waiters = {}
        self.closing = False
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
        library = self.catalogue.summaries()
        state["tasks"], state["library_page"] = page(library, self.desktop.library_offset)
        state["runtime"] = {**identity(), **getattr(self.desktop, "native_identity", {}), "adapter": self.desktop.adapter}
        state["runtime"]["input_mode"] = "development_injected" if getattr(self, "development_test_input", False) else "normal_filtered"
        state["connection_detail"] = "review_required" if self.desktop.playback.reviews() else ("ready" if self.native and self.native.returncode is None else "toolbar_closed")
        state["desktop_capabilities"] = {
            "format": FORMAT, "version": 1, "action_versions": [2, 3],
            "capture": True, "playback": True,
            "library_management": True, "popup_reopen": True,
            "actions": playback_capabilities(),
        }
        r = self.desktop.recording
        run = self.desktop.playback.run
        if r.state != "idle":
            state["tasks"].append(dict(id=r.task["id"], name=r.task["name"], format=FORMAT,
                format_version=1, playback_available=False, inputs=[], steps=len(r.task["actions"]),
                revision=None, duration_ms=r.elapsed_ms, updated_at=None, result="Unsaved desktop recording"))
            state.update(mode={"recording":"recording", "paused":"recording_paused",
                               "draft":"draft", "interrupted":"interrupted"}[r.state],
                         recording=r.state == "recording", message=r.problem or self.desktop.message,
                         active_task_id=r.task["id"], active_task_name=r.task["name"], selected_id=r.task["id"],
                         step=len(r.task["actions"]), total=len(r.task["actions"]))
        elif self.desktop.pending_play:
            selected = next(t for t in library if t["id"] == self.desktop.pending_play["task_id"])
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
                         active_task_name=next((t["name"] for t in library if t["id"] == run["task_id"]), "Desktop recording"),
                         selected_id=run["task_id"],
                         can_resume=run["pause_requested"])
        elif self.last_engine == "desktop":
            # A completed desktop save owns this projection. Legacy browser Stop
            # state must not leak into an idle native session or its selection.
            state.update(mode="idle", message=self.desktop.message, recording=False,
                         active_task_id=None, active_task_name="", step=0, total=0,
                         can_resume=False, selected_id=self.desktop.preview_task_id)
        # Results are projections of durable run journals, never saved-definition edits.
        for history in [*self.desktop.recovered_runs, *([run] if run else [])]:
            for row in state["tasks"]:
                if row["id"] == history["task_id"] and row.get("revision") == history["revision"]:
                    row["result"] = {"uncertain":"interrupted", "playing":"running"}.get(history["state"], history["state"])
        return state

    async def publish_native(self, state=None):
        if self.native and self.native.returncode is None:
            frame = wire(state or self.desktop.state())
            self.native.stdin.write(frame)
            await asyncio.wait_for(self.native.stdin.drain(), timeout=3)
        self.notify_state()

    async def apply_native(self, command):
        self.control_trace("native", command.get("kind"), command.get("id"))
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
            if command.get("kind") == "diagnostic" and command.get("payload", {}).get("kind") == "toolbar_ready":
                if self.native_ready and not self.native_ready.done():
                    if command["payload"].get("protocol") != 2 or command["payload"].get("build") != identity()["build"]:
                        self.native_ready.set_exception(Invalid("Incompatible toolbar build or IPC protocol. Rebuild the local candidate."))
                    else:
                        self.native_ready.set_result(None)
                        if self.desktop.message == "Native toolbar disconnected. Review the preserved recording or run before continuing.":
                            self.desktop.message = "Native toolbar reconnected. Review any preserved recording or interrupted run before continuing."
                            # Rebuild the projection so a draft's specific problem
                            # still takes precedence over connection status.
                            state = self.desktop.state()
                            state["ack"] = command.get("id")
            waiter = self.capture_waiters.get(command.get("payload", {}).get("request_id"))
            if waiter and command.get("kind") == waiter[0] and not waiter[1].done():
                waiter[1].set_result(None)
        await self.publish_native(state)

    async def open_toolbar(self):
        if self.closing:
            raise Invalid("The helper is shutting down. Restart it before continuing.")
        if self.native and self.native.returncode is None:
            return
        if self.native_pump and not self.native_pump.done():
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(self.native_pump, timeout=2)
        executable = native_path()
        if not executable.is_file():
            raise Invalid("Update required: native recorder package is missing.")
        verified = verify_package(executable)
        from .ocr_runtime import configure
        configure(self.store.root)
        self.desktop.native_identity = {"native_sha256": verified["native_sha256"]}
        if not self.deadline_watch or self.deadline_watch.done():
            self.deadline_watch = asyncio.create_task(self.watch_deadlines())
        # Only the local development launcher sets this flag; no API or saved
        # setting can enable it. The root guard prevents use with installed data.
        self.native_ready = asyncio.get_running_loop().create_future()
        self.native = await asyncio.create_subprocess_exec(
            str(executable), *native_arguments(self.store.root, getattr(self, "development_test_input", False)), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            limit=65538)
        self.native_pump = asyncio.create_task(self.read_native(self.native))
        try:
            await self.publish_native()
            await asyncio.wait_for(self.native_ready, timeout=5)
        except (asyncio.TimeoutError, ConnectionError, OSError, Invalid) as error:
            if self.native.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    self.native.terminate()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self.native.wait(), timeout=3)
            if isinstance(error, Invalid):
                raise
            raise Invalid("The Windows popup could not open. Close any other recorder popup, then try New recording again.") from None

    async def watch_deadlines(self):
        while not self.closing:
            await asyncio.sleep(.25)
            async with self.native_lock:
                if self.desktop.expire_start():
                    await self.publish_native()

    async def read_native(self, process=None):
        process = process or self.native
        failure = None
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                if len(line) > 65536 or not line.endswith(b"\n"):
                    raise Invalid("Native connection frame exceeded its bound.")
                async with self.native_lock:
                    if process is not self.native:
                        return
                    command = json.loads(line)
                    if not isinstance(command, dict):
                        raise Invalid("Native command must be an object.")
                    await self.apply_native(command)
        except Exception as error:
            if process is self.native:
                failure = "Native connection interrupted: " + type(error).__name__ + ". Review preserved state; no command will be repeated."
        finally:
            if process is self.native:
                if process.returncode == 79:
                    failure = "Helper acknowledgement deadline expired. Capture and playback stopped; review the preserved state."
                self.native_disconnected(failure)

    def native_disconnected(self, reason=None):
        if self.native_ready and not self.native_ready.done():
            self.native_ready.set_exception(ConnectionError("Popup closed before it was ready."))
        self.desktop.message = reason or "Native toolbar disconnected. Review the preserved recording or run before continuing."
        self.desktop.pending_play = None
        self.desktop.instruct("disarm")
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

    def control_trace(self, source, kind, command_id=None):
        """Bounded control provenance only; never include payloads or field values."""
        if kind not in {"record", "play", "stop", "play_stop", "pause", "resume",
                        "save", "interrupt", "connection_lost"}:
            return
        path = self.desktop.repository.root.parent / "control-provenance.json"
        try:
            rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            if not isinstance(rows, list):
                rows = []
            run = self.desktop.playback.run
            row = dict(at=datetime.now(timezone.utc).isoformat(), source=source, kind=kind,
                       recording=self.desktop.recording.state,
                       playback=run["state"] if run else None,
                       pending_play=bool(self.desktop.pending_play))
            if command_id is not None:
                from uuid import UUID
                row["command_id"] = str(UUID(command_id))
            self.desktop.repository.atomic(path, [*rows[-99:], row])
        except (OSError, ValueError, TypeError):
            pass  # Diagnostics must never prevent Stop.

    async def connection_lost(self, revoked=False):
        """Interrupt active work once; reconnect retries never touch a saved draft."""
        r, run = self.desktop.recording, self.desktop.playback.run
        capture_active = r.state in {"recording", "paused"}
        playback_active = bool(self.desktop.pending_play or (run and (
            run["state"] in {"playing", "paused"} or
            (run["state"] == "uncertain" and not run.get("result_received") and
             not self.desktop.playback.stop_event.is_set()))))
        reason = ("This PC was disconnected from OS. Reconnect it before continuing." if revoked else
                  "OS connection lost. Review the preserved draft or run; reconnecting will not resume it.")
        if capture_active or playback_active:
            self.control_trace("connection", "connection_lost")
            self.last_engine = "desktop"
            if capture_active:
                try:
                    await self.desktop_command("stop", {}, str(uuid4()), source="connection")
                except (asyncio.TimeoutError, ConnectionError):
                    pass  # The bounded barrier already preserved the draft.
                r.interrupt(reason)
            self.desktop.pending_play = None
            self.desktop.playback.stop(reason=reason)
            self.desktop.instruct("disarm")
            self.desktop.message = reason
            await self.publish_native()
        # Keep the legacy browser engine's existing cancellation behaviour.
        if super().busy() or self.recording or self.mode == "recording_paused":
            await super().stop()
            self.mode, self.message = "interrupted", reason

    async def stop_from_device(self):
        await self.stop(source="os")

    async def desktop_command(self, kind, data, command_id, *, source="os"):
        self.control_trace(source, kind, command_id)
        if kind == "library-page":
            self.desktop.apply(dict(v=1, id=command_id, kind="library_page", payload=data))
            await self.publish_native()
            return {"message":"Library page loaded."}
        if kind != "inspect":
            self.last_engine = "desktop"
        if kind == "inspect":
            task = self.desktop.repository.get(data["id"])
            return {"task":task, "revision":self.store.revision(task), "values":{},
                    "desktop":True, "playback_available":True}
        if kind in {"rename", "delete"}:
            if self.busy() or self.recording:
                raise Invalid("Stop and save the current task before changing the library.")
            result = self.desktop.repository.manage(data["id"], name=data.get("name"), deleted=kind == "delete")
            await self.publish_native()
            tasks, cursor = page(self.catalogue.summaries(), self.desktop.library_offset)
            return {**result, "tasks": tasks, "library_page": cursor}
        await self.open_toolbar()
        if kind in {"record", "open-popup"}:
            if super().busy() or self.recording:
                raise Invalid("Stop the current session first.")
            if not self.desktop_busy():
                self.desktop.message = "Choose a window and press Record in the Windows popup."
            await self.publish_native({**self.desktop.state(), "show_toolbar": True})
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
            await self.publish_native({**self.desktop.state(), "show_toolbar": True} if kind == "play" else None)
        return {"message":self.desktop.message}

    def is_desktop(self, task_id):
        return self.catalogue.is_desktop(task_id)

    async def stop(self, *, source="helper"):
        if self.closing:
            await super().stop()
        elif self.desktop_busy():
            await self.desktop_command("stop", {}, str(uuid4()), source=source)
        else:
            await super().stop()

    async def close(self):
        self.closing = True
        if self.deadline_watch:
            self.deadline_watch.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.deadline_watch
        self.desktop.playback.stop()
        self.desktop.pending_play = None
        if self.desktop.recording.state in {"recording", "paused"}:
            self.desktop.recording.interrupt("Helper stopped. Review the preserved draft before continuing.")
        if self.native and self.native.returncode is None:
            self.desktop.instruct("disarm")
            with contextlib.suppress(Exception):
                await self.publish_native()
            with contextlib.suppress(ProcessLookupError):
                self.native.terminate()
            try:
                await asyncio.wait_for(self.native.wait(), timeout=5)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self.native.kill()
                await asyncio.wait_for(self.native.wait(), timeout=5)
        if self.native and self.native.stdin:
            self.native.stdin.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.native.stdin.wait_closed(), timeout=1)
        if self.native_pump:
            with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
                await asyncio.wait_for(self.native_pump, timeout=2)
        await super().close()
