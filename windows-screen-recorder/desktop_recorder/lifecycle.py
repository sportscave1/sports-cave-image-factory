"""Serialized coordinator for a future visible toolbar and capture adapter.

Call on one coordinator thread. A native provider must marshal events here.
No global hooks, screenshots, browser launch or task execution lives here.
"""
from copy import deepcopy
from datetime import datetime
from time import monotonic
from uuid import uuid4
from .contract import FORMAT, Invalid, validate


class Recording:
    def __init__(self, repository, clock=monotonic, capacity=500):
        if not 1 <= capacity <= 500:
            raise ValueError("Capacity must be 1–500.")
        self.repository, self.clock, self.capacity = repository, clock, capacity
        self.state = "idle"
        self.task = None
        self.total = 0.0
        self.started = None
        self.generation = 0
        self.problem = None

    @property
    def elapsed_ms(self):
        return int(1000 * (self.total + (self.clock() - self.started if self.started is not None else 0)))

    def _freeze(self):
        if self.started is not None:
            self.total += self.clock() - self.started
            self.started = None

    def _checkpoint(self):
        self.repository.checkpoint(self.task, self.state, self.elapsed_ms)

    def record(self, starting_context, *, indicator_visible):
        if self.state != "idle" or not indicator_visible:
            raise Invalid("Show recording controls and save/discard the existing draft first.")
        self.task = validate(dict(format=FORMAT, version=1, id=str(uuid4()),
                                  name="Recording " + datetime.now().strftime("%d %b %Y %H.%M"),
                                  starting_context=starting_context, actions=[]))
        self.total, self.problem = 0.0, None
        self.state = "recording"
        self.started = self.clock()
        self.generation += 1
        try:
            self._checkpoint()
        except Exception:
            self._freeze()
            self.state = "interrupted"
            raise
        return self.generation

    def accept(self, action, *, generation, privacy, toolbar=False):
        # Drop late events without examining their values. Provider must gate before
        # reading field contents too. Unknown privacy is not permission to read.
        if self.state != "recording" or generation != self.generation or toolbar:
            return False
        if privacy != "safe":
            self.interrupt("Secure or unclassified control; capture suspended.")
            return False
        if len(self.task["actions"]) >= self.capacity:
            self.interrupt("Recording capacity reached; no further actions captured.")
            return False
        try:
            candidate = validate({**self.task, "actions": self.task["actions"] + [action]})
        except (Invalid, TypeError):
            self.interrupt("Unsupported interaction; capture suspended. Review before saving.")
            return False
        self.task = candidate
        try:
            self._checkpoint()
        except Exception:
            self._freeze()
            self.state = "interrupted"
            self.generation += 1
            self.problem = "Draft write failed; capture suspended. Stop to retry."
            raise
        return True

    def pause(self, flush):
        if self.state != "recording":
            raise Invalid("Not recording.")
        # Provider synchronously quiesces and delivers its pre-barrier events.
        # No event after the barrier may share this generation.
        try:
            flush()
        except Exception:
            self.interrupt("Capture flush failed; draft retained.")
            raise
        if self.state != "recording":
            return
        self._freeze()
        self.state = "paused"
        self.generation += 1
        self._checkpoint()

    def resume(self, *, indicator_visible):
        if self.state != "paused" or not indicator_visible:
            raise Invalid("Only a visible paused recording can resume.")
        self.started = self.clock()
        self.state = "recording"
        self.generation += 1
        try:
            self._checkpoint()
        except Exception:
            self._freeze()
            self.state = "interrupted"
            self.generation += 1
            self.problem = "Resume could not preserve the draft. Capture remains suspended."
            raise
        return self.generation

    def stop(self, flush=lambda: None):
        if self.state not in {"recording", "paused", "interrupted", "draft"}:
            raise Invalid("No recording to stop.")
        if self.state == "recording":
            self.pause(flush)
        self._freeze()
        self.state = "draft"
        self.generation += 1
        self._checkpoint()  # Save dialog should appear only after this succeeds.
        return deepcopy(self.task)

    def interrupt(self, reason):
        self._freeze()
        self.state, self.problem = "interrupted", reason
        self.generation += 1
        self._checkpoint()

    def save(self, name):
        if self.state != "draft":
            raise Invalid("Stop before Save.")
        if self.problem:
            raise Invalid(self.problem)
        task = validate({**self.task, "name": name})
        result = self.repository.save(task, duration_ms=self.elapsed_ms)  # Never calls Play.
        self.state = "idle"
        self.task = None
        return result

    def recover(self):
        if self.state != "idle":
            raise Invalid("Already active.")
        draft = self.repository.load_draft()
        if draft is not None:
            self.task = draft["task"]
            self.total = draft["elapsed_ms"] / 1000
            self.state = "interrupted"
            self.problem = "Recovered after interruption; review or discard before continuing."
            self.generation += 1
        return deepcopy(draft)

    def discard(self):
        if self.state not in {"draft", "interrupted"}:
            raise Invalid("Stop before discarding.")
        self.repository.checkpoint(self.task, "discarded", self.elapsed_ms)
        self.task, self.problem, self.state = None, None, "idle"
