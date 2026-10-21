"""Serialized execution journal. Native execution is supplied through a port.

An action is marked uncertain durably BEFORE dispatch. Only an explicit result
can complete it. Reopening a run never dispatches it again.
"""
from copy import deepcopy
from threading import Event, RLock
from uuid import UUID

from .contract import Invalid
from .integration import prepare_play


class Playback:
    def __init__(self, repository):
        self.repository = repository
        self.root = repository.root / "runs"
        self.root.mkdir(exist_ok=True)
        self.lock = RLock()
        self.stop_event = Event()
        self.ready = Event()
        self.ready.set()
        self.run = None

    def _write(self):
        self.repository.atomic(self.root / (self.run["id"] + ".json"), self.run)

    def begin(self, run_id, task_id, revision, capabilities, *,
              controls_visible, emergency_stop_ready):
        with self.lock:
            if str(UUID(run_id)) != run_id:
                raise Invalid("Invalid run ID.")
            if self.run and self.run["state"] in {"playing", "paused", "uncertain"}:
                raise Invalid("Stop or reconcile the current run first.")
            if (self.root / (run_id + ".json")).exists():
                raise Invalid("This Play command already has a journal. It will not run again.")
            import json
            for path in self.root.glob("*.json"):
                prior = json.loads(path.read_text(encoding="utf-8"))
                if prior["task_id"] == task_id and prior["state"] == "uncertain":
                    raise Invalid("This task has an uncertain previous action. Reconcile its result before starting another run.")
            task = self.repository.get(task_id)
            if self.repository.revision(task) != revision:
                raise Invalid("Saved revision changed. Select the task again.")
            checked = prepare_play(task, capabilities, explicit_play=True,
                                   controls_visible=controls_visible,
                                   emergency_stop_ready=emergency_stop_ready)
            self.run = dict(id=run_id, task_id=task_id, revision=revision,
                            state="playing", next_step=0, total=len(checked["actions"]),
                            pending=None, results=[], pause_requested=False)
            self.stop_event.clear()
            self.ready.set()
            self._write()
            return checked

    def dispatch(self, index):
        with self.lock:
            if not self.run or self.run["state"] != "playing" or self.stop_event.is_set():
                raise Invalid("Playback is not running.")
            if self.run["pending"] is not None or index != self.run["next_step"]:
                raise Invalid("Action already dispatched or out of order.")
            self.run["pending"] = index
            self.run["result_received"] = False
            self.run["state"] = "uncertain"
            self._write()  # A failed write prevents the caller sending input.

    def acknowledge(self, index, *, verified, message="", no_effect=False):
        with self.lock:
            if not self.run or self.run["pending"] != index or self.run.get("result_received"):
                raise Invalid("Unexpected action acknowledgement.")
            self.run["result_received"] = True
            if not verified:
                self.run["pause_requested"] = False
                self.run["message"] = self.run.get("stop_reason") or str(message)[:240] or "Action outcome is uncertain. Check the application."
                if no_effect is True:
                    self.run["results"].append(dict(step=index, verified=False, no_effect=True))
                    self.run["pending"] = None
                    self.run["state"] = "stopped"
                self._write()
                return
            self.run["results"].append(dict(step=index, verified=True))
            self.run["pending"] = None
            self.run["next_step"] = index + 1
            self.run["state"] = ("stopped" if self.stop_event.is_set() else
                                 "completed" if index + 1 == self.run["total"] else
                                 "paused" if not self.ready.is_set() else "playing")
            self._write()

    def pause(self):
        with self.lock:
            self.ready.clear()
            if self.run:
                self.run["pause_requested"] = True
            if self.run and self.run["state"] == "playing":
                self.run["state"] = "paused"
            if self.run:
                self._write()

    def resume(self):
        with self.lock:
            if not self.run or not self.run["pause_requested"]:
                raise Invalid("Only a paused, confirmed run can resume.")
            self.run["pause_requested"] = False
            self.run["state"] = "playing" if self.run["pending"] is None else "uncertain"
            self._write()
            self.ready.set()

    def stop(self, reason=None):
        self.stop_event.set()
        self.ready.set()
        with self.lock:
            if self.run and self.run["state"] not in {"completed", "stopped"}:
                if reason:
                    self.run["stop_reason"] = str(reason)[:240]
                    self.run["message"] = self.run["stop_reason"]
                # Stop cannot turn an unknown side effect into a known failure.
                if self.run["pending"] is None:
                    self.run["state"] = "stopped"
                self._write()

    def recover(self):
        import json
        recovered = []
        with self.lock:
            for path in sorted(self.root.glob("*.json"), key=lambda path:path.stat().st_mtime_ns):
                run = json.loads(path.read_text(encoding="utf-8"))
                if run["state"] == "uncertain" and run.get("result_received") and run["pending"] is not None:
                    task = self.repository.get(run["task_id"], include_removed=True)
                    if (self.repository.revision(task) == run["revision"] and
                            task["actions"][run["pending"]]["kind"] == "focus_window"):
                        run["reconciliation"] = "Returned focus-only failure; no application action dispatched. Explicit Play required."
                        run["pending"] = None
                        run["state"] = "stopped"
                        self.repository.atomic(path, run)
                if run["state"] in {"playing", "paused", "uncertain"}:
                    run["state"] = "uncertain" if run["pending"] is not None else "stopped"
                    run["message"] = "Helper restarted. No action was repeated."
                    self.repository.atomic(path, run)
                recovered.append(deepcopy(run))
        return recovered

    def reconcile_observed_result(self, run_id, revision, step, evidence):
        """Explicit operator observation closes uncertainty without replay or pass."""
        import json
        if str(UUID(run_id)) != run_id or not isinstance(evidence, str) or not evidence.strip():
            raise Invalid("A specific run and operator observation are required.")
        with self.lock:
            path = self.root / (run_id + ".json")
            run = json.loads(path.read_text(encoding="utf-8"))
            if (run["state"] != "uncertain" or not run.get("result_received") or
                    run["revision"] != revision or run["pending"] != step):
                raise Invalid("This result is not available for reconciliation.")
            task = self.repository.get(run["task_id"])
            if self.repository.revision(task) != revision:
                raise Invalid("The saved task revision changed.")
            run["reconciliation"] = dict(step=step, evidence=evidence[:500],
                                         disposition="Operator observed effect; run not counted as completed.")
            run["state"], run["pending"] = "stopped", None
            self.repository.atomic(path, run)
            if self.run and self.run["id"] == run_id:
                self.run = run
            return deepcopy(run)
