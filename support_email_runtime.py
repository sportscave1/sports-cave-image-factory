"""Process-local IMAP admission, backoff and short-lived display snapshots.

No sockets, credentials, bodies or durable state live here. A single Render
process shares this coordinator across browser tabs; mailbox identities include
the provider's credential fingerprint. Notification deduplication stays durable
in the existing notification store.
"""
from collections import OrderedDict, deque
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import threading
import time

POLL_SECONDS = 60
_BACKGROUND = ContextVar("email_background", default=False)
_FORCE = ContextVar("email_force", default=False)


class Deferred(RuntimeError):
    """A check was skipped, not a new failed connection."""
    def __init__(self, message, *, reason="busy"):
        super().__init__(message)
        self.reason = reason


@contextmanager
def operation(*, background=False, force=False):
    bg, forced = _BACKGROUND.set(background), _FORCE.set(force)
    try:
        yield
    finally:
        _BACKGROUND.reset(bg)
        _FORCE.reset(forced)


class MailboxRuntime:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.condition = threading.Condition(threading.RLock())
        self.states = OrderedDict()
        self.cache = OrderedDict()
        self.inflight = set()
        self.active = self.background_active = self.foreground_waiting = 0

    def _state(self, scope):
        if scope not in self.states:
            # Configuration rotation cannot grow state indefinitely.
            if len(self.states) >= 16:
                self.states.popitem(last=False)
            self.states[scope] = {"failures": 0, "retry_at": 0, "generation": 0, "background_starts": deque(),
                                  "last_success_at": None, "last_failure_at": None,
                                  "failure_stage": None, "watcher_state": "unavailable", "fallback_state": "ready"}
        self.states.move_to_end(scope)
        return self.states[scope]

    def generation(self, scope):
        with self.condition:
            return self._state(scope)["generation"]

    def watcher(self, scope, state):
        # Watcher health is diagnostic only: it never opens the foreground circuit.
        if state not in {"healthy", "reconnecting", "unavailable"}:
            raise ValueError("Invalid watcher state")
        with self.condition:
            self._state(scope)["watcher_state"] = state

    def health(self, scope):
        with self.condition:
            state = self._state(scope)
            if state["failures"]:
                health = "RECONNECTING" if state["last_success_at"] is not None else "UNAVAILABLE"
            else:
                health = "HEALTHY" if state["watcher_state"] == "healthy" else "DEGRADED"
            return {"state": health, "consecutive_failures": state["failures"],
                    **{k: state[k] for k in ("last_success_at", "last_failure_at", "failure_stage",
                                            "watcher_state", "fallback_state")}}

    def invalidate(self, scope):
        with self.condition:
            self._state(scope)["generation"] += 1
            for key in list(self.cache):
                if key[0] == scope:
                    del self.cache[key]

    def get(self, scope, key):
        with self.condition:
            entry = self.cache.get((scope, key))
            if entry and self.clock() < entry[0]:
                self.cache.move_to_end((scope, key))
                return deepcopy(entry[1])
            self.cache.pop((scope, key), None)
        return None

    def put(self, scope, key, value, generation):
        with self.condition:
            if generation != self._state(scope)["generation"]:
                return  # A foreground action/refresh superseded this poll.
            # Headers/flags only, bounded both by entry count and serialized size.
            if len(repr(value)) > 512 * 1024:
                return
            self.cache[(scope, key)] = (self.clock() + POLL_SECONDS, deepcopy(value))
            while len(self.cache) > 16:
                self.cache.popitem(last=False)

    def check(self, scope, key, loader):
        cached = self.get(scope, key)
        if cached is not None:
            return cached
        identity = (scope, key)
        with self.condition:
            if identity in self.inflight:
                raise Deferred("Mailbox check is already running.")
            self.inflight.add(identity)
            generation = self._state(scope)["generation"]
        try:
            with operation(background=True):
                result = loader()
            if generation != self.generation(scope):
                raise Deferred("Mailbox check superseded by a foreground action.")
            self.put(scope, key, result, generation)
            return result
        finally:
            with self.condition:
                self.inflight.discard(identity)

    @contextmanager
    def connection(self, scope, *, timeout=8, background=False):
        background = background or _BACKGROUND.get()
        with self.condition:
            state = self._state(scope)
            if self.clock() < state["retry_at"] and not _FORCE.get():
                raise Deferred("Connection interrupted. Reconnecting automatically.", reason="backoff")
            if background:
                # Reserve capacity for clicks; background checks never queue sockets.
                if self.active >= 1 or self.background_active or self.foreground_waiting:
                    raise Deferred("Mailbox check deferred for an active operation.")
                starts = state["background_starts"]
                while starts and starts[0] <= self.clock() - 60:
                    starts.popleft()
                if len(starts) >= 6:
                    raise Deferred("Mailbox background check budget reached.")
                starts.append(self.clock())
            else:
                self.foreground_waiting += 1
                try:
                    if not self.condition.wait_for(lambda: self.active < 1, timeout=timeout):
                        raise Deferred("Mailbox is busy. Try again shortly.", reason="connection_budget_timeout")
                finally:
                    self.foreground_waiting -= 1
            self.active += 1
            self.background_active += int(background)
        try:
            yield
        except BaseException as error:
            # Cancellation and local validation failures do not poison connectivity.
            code = getattr(error, "code", "")
            if code in {"timeout", "dns", "temporary", "tls", "authentication", "folders",
                        "status", "refused", "network", "reset", "bye", "limit", "protocol"}:
                with self.condition:
                    state = self._state(scope)
                    state["failures"] = min(4, state["failures"] + 1)
                    state.update(last_failure_at=time.time(), failure_stage=getattr(error, "stage", "operation"),
                                 fallback_state="backoff")
                    state["retry_at"] = self.clock() + min(120, 15 * 2 ** (state["failures"] - 1))
                    self.invalidate(scope)
            raise
        else:
            with self.condition:
                self._state(scope).update(failures=0, retry_at=0, last_success_at=time.time(), fallback_state="ready")
        finally:
            with self.condition:
                self.active -= 1
                self.background_active -= int(background)
                self.condition.notify_all()


RUNTIME = MailboxRuntime()
