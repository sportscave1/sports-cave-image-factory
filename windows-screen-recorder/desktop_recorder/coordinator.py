"""Native child uses inherited anonymous pipes, not a listening control socket."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from .dependencies import load
from .integration import Repository
from .lifecycle import Recording
from .contract import Invalid
from .playback import Playback
from .receipts import Receipts


class Coordinator:
    def __init__(self, root):
        load(root)
        from task_recorder.store import atomic, Store
        self.repository = Repository(root, atomic, Store.revision)
        self.recording = Recording(self.repository)
        self.recording.recover()
        self.receipts = Receipts(root)
        self.message = "Choose a window, then Record."
        self.last_saved = None
        self.diagnostics = []
        self.playback = Playback(self.repository)
        self.recovered_runs = self.playback.recover()
        self.play_task = None
        self.pending_play = None
        self.native_instruction = None
        self.instruction_serial = 0

    def instruct(self, kind, **data):
        self.instruction_serial += 1
        self.native_instruction = dict(serial=self.instruction_serial, kind=kind, **data)

    def next_step(self):
        run = self.playback.run
        if run["state"] == "playing":
            index = run["next_step"]
            self.playback.dispatch(index)
            self.instruct("execute", step=index, action=self.play_task["actions"][index])
        elif run["state"] != "paused":
            self.instruct("disarm")

    def state(self):
        r = self.recording
        run = self.playback.run
        playing = self.pending_play is not None or (run and
            (run["state"] in {"playing", "paused"} or
             (run["state"] == "uncertain" and not run.get("result_received"))))
        rows = []
        if r.state == "idle" and not playing:
            for path, metadata in self.repository.visible():
                task = self.repository.get(path.stem)
                rows.append(dict(id=task["id"], name=self.repository.display_name(task), revision=self.repository.revision(task)))
        context = r.task
        if self.pending_play:
            context = self.repository.get(self.pending_play["task_id"])
        elif playing:
            context = self.play_task
        return dict(v=1, state=("playing" if playing else r.state), generation=r.generation,
                    elapsed_ms=r.elapsed_ms, message=r.problem or self.message,
                    last_saved=self.last_saved, tasks=rows,
                    instruction=self.native_instruction, run=run,
                    recording_name=self.repository.display_name(context) if context else "",
                    suggested_name=r.task["name"] if r.task else "")

    def apply(self, command):
        if not isinstance(command, dict) or set(command) != {"v", "id", "kind", "payload"} or type(command["v"]) is not int or command["v"] != 1:
            raise Invalid("Unknown IPC contract.")
        if not isinstance(command["payload"], dict):
            raise Invalid("Invalid command payload.")
        from uuid import UUID
        if str(UUID(command["id"])) != command["id"]:
            raise Invalid("Invalid command ID.")
        fingerprint = hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()
        previous = self.receipts.lookup(command["id"], fingerprint)
        if previous is not None:
            if previous.get("last_saved"):
                self.last_saved = previous["last_saved"]
            return {**self.state(), "ack": command["id"]}
        self.receipts.begin(command["id"], fingerprint)
        r, data, kind = self.recording, command["payload"], command["kind"]
        if kind == "play":
            if r.state != "idle" or self.pending_play or (self.playback.run and self.playback.run["state"] in {"playing", "paused", "uncertain"}):
                raise Invalid("Finish the current recording or run first.")
            task = self.repository.get(data["id"])
            if self.repository.revision(task) != data["revision"]:
                raise Invalid("Select the current saved revision.")
            if not task["actions"]:
                raise Invalid("This preserved draft has no actions to play.")
            if any(a["version"] != 2 for a in task["actions"]):
                raise Invalid("This early desktop draft lacks scoped targets. Record a new task; the original is unchanged.")
            self.pending_play = dict(run_id=command["id"], task_id=data["id"], revision=data["revision"])
            self.instruct("arm", require_local_confirmation=data.get("confirm_on_toolbar") is True)
            self.message = "Starting. Confirm Start playback on the Windows toolbar if requested."
        elif kind == "play_ready":
            if not self.pending_play:
                raise Invalid("No pending Play.")
            from .contract import CAPABILITIES
            try:
                self.play_task = self.playback.begin(**self.pending_play, capabilities=[c.replace(".v1", ".v2") for c in CAPABILITIES.values()],
                                                     controls_visible=True, emergency_stop_ready=True)
            except Exception:
                self.pending_play = None
                self.instruct("disarm")
                raise
            self.pending_play = None
            self.message = "Playing. Ctrl+Alt+F12 stops immediately."
            self.next_step()
        elif kind == "play_result":
            self.playback.acknowledge(data["step"], verified=data["verified"] is True,
                                      message=data.get("message", ""), no_effect=data.get("no_effect") is True)
            run = self.playback.run
            self.message = run.get("message") or ("Completed" if run["state"] == "completed" else
                                                 f"Verified {run['next_step']} of {run['total']} actions.")
            if data["verified"] is True:
                self.next_step()
            else:
                self.message = "Stopped. " + self.message
                self.instruct("disarm")
        elif kind == "play_stop":
            self.playback.stop(reason=str(data.get("reason", "Playback stopped."))[:240])
            self.pending_play = None
            self.instruct("disarm")
            self.message = str(data.get("reason", "Playback stopped."))[:240]
        elif kind == "play_pause":
            self.playback.pause()
            self.instruct("pause")
            self.message = "Pause requested; any in-flight action must first be confirmed."
        elif kind == "play_resume":
            self.playback.resume()
            self.message = "Playing"
            self.instruct("resume")
            if self.playback.run["pending"] is None:
                self.next_step()
        elif kind == "record":
            if self.pending_play or (self.playback.run and self.playback.run["state"] in {"playing", "paused", "uncertain"}):
                raise Invalid("Finish or reconcile playback before recording.")
            from .contract import identity
            selected = identity(data["window"])
            r.record({"mode": "prepared", "binding": None, "window": selected}, indicator_visible=True)
            self.playback.run = None  # Historical run remains in its durable journal.
            self.message = "Recording supported actions. Prepared windows remain unchanged."
        elif kind == "event":
            r.accept(data["action"], generation=data["generation"], privacy=data["privacy"])
            self.message = str(len(r.task["actions"]) if r.task else 0) + " actions captured"
        elif kind == "pause":
            if r.state == "recording":
                r.pause(lambda: None)  # Native pipe message follows its flush barrier.
            self.message = "Paused. Actions are excluded."
        elif kind == "resume":
            r.resume(indicator_visible=True)
            self.message = "Recording"
        elif kind == "stop":
            if r.state != "idle":
                r.stop()
            self.message = "Name and save your recording."
        elif kind == "interrupt":
            self.message = str(data.get("reason", "Capture interrupted"))[:240]
            if r.task is not None:
                r.interrupt(self.message)
        elif kind == "review":
            if r.state != "interrupted":
                raise Invalid("No interrupted draft.")
            # Explicit partial-save review; incomplete recording remains identified.
            self.message = "Review: " + str(len(r.task["actions"])) + " preserved actions. Save keeps only these actions; nothing will play."
            r.stop()
            r.problem = None
        elif kind == "save":
            if r.state == "idle" and self.last_saved:
                self.receipts.complete(command["id"], {"last_saved": self.last_saved})
                return {**self.state(), "ack": command["id"]}
            before = time.perf_counter()
            self.last_saved = r.save(data["name"])
            self.last_saved["save_ms"] = round((time.perf_counter() - before) * 1000, 2)
            self.message = "Saved. Nothing has been executed."
        elif kind == "discard":
            if r.state != "idle":
                r.discard()
            self.message = "Draft discarded."
        elif kind == "diagnostic":
            self.diagnostics.append(data)
            self.diagnostics = self.diagnostics[-30:]
            self.repository.atomic(self.repository.root.parent / "native-diagnostics.json", self.diagnostics)
            if data.get("kind") == "unsupported_click":
                self.message = "Unsupported control metadata preserved."
            elif "dpi" in data:
                self.message = "Details: DPI " + str(data["dpi"]) + "; monitors " + str(data.get("monitors")) + ". Metadata only."
        elif kind == "close":
            if r.state != "idle" or self.pending_play:
                raise Invalid("Save or discard before closing.")
            self.playback.stop()
        else:
            raise Invalid("Unsupported native command.")
        self.receipts.complete(command["id"], {"last_saved": self.last_saved if kind == "save" else None})
        return {**self.state(), "ack": command["id"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--accept-injected-test-input", action="store_true")
    args = parser.parse_args()
    root = args.data.resolve()
    protected = Path(os.environ["LOCALAPPDATA"]) / "SportsCaveOS"
    if protected == root or protected in root.parents:
        raise SystemExit("Development launcher refuses installed helper storage.")
    root.mkdir(parents=True, exist_ok=True)
    from .dependencies import load
    load(root)
    from task_recorder.server import instance_lock
    with instance_lock(root / "candidate.lock"):
        coordinator = Coordinator(root)
        native = Path(__file__).resolve().parents[1] / "native/bin/DesktopRecorder.exe"
        command = [str(native), "--candidate"]
        if args.accept_injected_test_input:
            command.append("--accept-injected-test-input")
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        (root / "candidate-process.json").write_text(json.dumps({"coordinator": os.getpid(), "native": child.pid}))
        def publish(state):
            child.stdin.write(json.dumps(state, ensure_ascii=True) + "\n")
            child.stdin.flush()
            # Non-secret UI projection; actual catalogue integration is a separate adapter.
            coordinator.repository.atomic(root / "candidate-state.json", state)
        publish(coordinator.state())
        try:
            while True:
                line = child.stdout.readline(65538)
                if not line:
                    break
                if len(line) > 65536 or not line.endswith("\n"):
                    raise Invalid("IPC message exceeds the bounded frame.")
                message = {}
                try:
                    message = json.loads(line)
                    state = coordinator.apply(message)
                except Exception as error:
                    if coordinator.recording.task:
                        try:
                            coordinator.recording.interrupt("Coordinator could not complete the command: " + type(error).__name__)
                        except OSError:
                            # Keep the latest in-memory task and previous durable
                            # checkpoint. A failed error checkpoint must not kill UI.
                            coordinator.recording.problem = "Disk write failed. Draft remains in memory; restore disk access, then review and Save."
                    coordinator.message = str(error)[:240]
                    state = coordinator.state()
                    if isinstance(message, dict):
                        state["ack"] = message.get("id")
                try:
                    publish(state)
                except OSError:
                    # publish writes the pipe first; the projection is not the draft.
                    if child.poll() is not None:
                        break
                if isinstance(message, dict) and message.get("kind") == "close" and coordinator.recording.state == "idle":
                    break
        finally:
            coordinator.playback.stop()
            if coordinator.recording.state in {"recording", "paused"}:
                coordinator.recording.interrupt("Candidate closed during recording. Review the preserved draft.")
            (root / "native-diagnostics.json").write_text(json.dumps(coordinator.diagnostics, indent=2))
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)
            error = child.stderr.read(8192)
            if error:
                (root / "native-error.txt").write_text(error, encoding="utf-8")


if __name__ == "__main__":
    main()
