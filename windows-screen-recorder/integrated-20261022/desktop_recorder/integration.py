"""Ports for the existing helper. No second relay, auth system or task database."""
from copy import deepcopy
from pathlib import Path
import json
import time
from threading import Event
from typing import Protocol
from contextlib import contextmanager
from .contract import Invalid, requirements, validate


class CapturePort(Protocol):
    def attach(self, windows, emit, generation): ...
    def quiesce_and_flush(self): ...
    def detach(self): ...


class ExecutionPort(Protocol):
    def validate_window(self, target): ...
    def resolve_unique_control(self, target): ...
    def wait_ready(self, target, timeout_ms, cancellation): ...
    def release_held_input(self): ...


class Repository:
    """Use existing store.atomic and Store.revision via dependency injection.

    Format-separated files under the existing helper data root; no DB or credentials.
    Do NOT construct this against production in Phase 1. Future task listing must
    explicitly merge namespaces, with capability negotiation, under the helper lock.
    """
    def __init__(self, root, atomic, revision):
        self.root = Path(root) / "desktop-v1"
        self.root.mkdir(parents=True, exist_ok=True)
        self.atomic, self.revision = atomic, revision
        self.library_path = self.root.parent / "desktop-library.json"
        self._library_stamp, self._library = None, {}

    def library(self):
        if not self.library_path.exists():
            return {}
        stat = self.library_path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        if stamp != self._library_stamp:
            self._library = json.loads(self.library_path.read_text(encoding="utf-8"))
            self._library_stamp = stamp
        return self._library

    def visible(self):
        metadata = self.library()
        return [(path, metadata.get(path.stem, {})) for path in self.root.glob("*.json")
                if path.name != "draft.json" and not metadata.get(path.stem, {}).get("deleted")]

    def display_name(self, task):
        return self.library().get(task["id"], {}).get("name", task["name"])

    def manage(self, task_id, *, name=None, deleted=False):
        task = self.get(task_id)
        if name is not None:
            name = validate({**task, "name": name})["name"]
        metadata = deepcopy(self.library())
        metadata[task_id] = {**metadata.get(task_id, {}), "deleted": deleted,
                             "updated_at": time.time() * 1000}
        if name is not None:
            metadata[task_id]["name"] = name
        # Library labels/removal never rewrite an immutable action definition,
        # saved revision, draft, receipt or run journal. Delete retains recovery data.
        self.atomic(self.library_path, metadata)
        return {"id": task_id, "name": self.display_name(task)}

    def checkpoint(self, task, state, elapsed_ms):
        self.atomic(self.root / "draft.json", {"task": validate(task), "state": state, "elapsed_ms": elapsed_ms})

    def load_draft(self):
        path = self.root / "draft.json"
        if not path.exists():
            return None
        draft = json.loads(path.read_text(encoding="utf-8"))
        draft["task"] = validate(draft["task"])
        if draft.get("state") == "discarded":
            return None
        if type(draft["elapsed_ms"]) is not int or draft["elapsed_ms"] < 0:
            raise Invalid("Invalid draft duration.")
        saved = self.root / (draft["task"]["id"] + ".json")
        if saved.exists():
            return None  # Save committed before a crash; never resurrect as unsaved.
        return draft

    def save(self, task):
        task = validate(task)
        path = self.root / (task["id"] + ".json")
        if path.exists():
            if self.revision(json.loads(path.read_text(encoding="utf-8"))) != self.revision(task):
                raise Invalid("Saved tasks are immutable. Editing requires a new ID.")
        else:
            self.atomic(path, task)
        return {"id": task["id"], "revision": self.revision(task)}

    def get(self, task_id, *, include_removed=False):
        from uuid import UUID
        try:
            if str(UUID(task_id)) != task_id:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise Invalid("Invalid task ID.") from None
        if not include_removed and self.library().get(task_id, {}).get("deleted"):
            raise Invalid("This recording was removed from the library.")
        return validate(json.loads((self.root / (task_id + ".json")).read_text(encoding="utf-8")))


class Cancellation:
    """Thread-safe signal; the native executor owns release on its input thread."""
    def __init__(self):
        self.requested = Event()

    def stop(self):
        self.requested.set()

    def check(self):
        if self.requested.is_set():
            raise InterruptedError("Playback stopped.")


@contextmanager
def input_scope(executor, cancellation):
    """Future executor cleanup boundary; this function never sends input."""
    try:
        cancellation.check()
        yield
        cancellation.check()
    finally:
        executor.release_held_input()


def prepare_play(task, available, *, explicit_play, controls_visible, emergency_stop_ready):
    """Pure preflight, never executes. Durable receipts remain DeviceAgent's job."""
    if not (explicit_play and controls_visible and emergency_stop_ready):
        raise Invalid("Explicit Play, visible progress and emergency Stop are required.")
    checked = validate(task)
    missing = requirements(checked) - set(available)
    if missing:
        raise Invalid("Missing capabilities: " + ", ".join(sorted(missing)))
    if not checked["actions"]:
        raise Invalid("Recording has no actions.")
    return deepcopy(checked)
