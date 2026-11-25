"""One bounded authenticated read connection. No writes or mailbox content."""
import threading
import time


class ReadConnectionSlot:
    def __init__(self, close, *, idle_seconds=10, lifetime_seconds=60,
                 clock=time.monotonic, timer=threading.Timer):
        self.lock = threading.RLock()
        self.closed = threading.Event()
        self.close_wire, self.clock, self.timer_factory = close, clock, timer
        self.idle_seconds, self.lifetime_seconds = idle_seconds, lifetime_seconds
        self.idle, self.timer, self.expires, self.born = None, None, 0, 0

    def discard(self):
        """Caller holds lock; a timer can never close a borrowed connection."""
        if self.timer:
            self.timer.cancel()
            self.timer = None
        wire, self.idle = self.idle, None
        if wire is not None:
            self.close_wire(wire)

    def take(self):
        if self.closed.is_set() or self.clock() >= self.expires:
            self.discard()
        wire, self.idle = self.idle, None
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if wire is None:
            self.born = self.clock()
        return wire

    def keep(self, wire):
        if self.closed.is_set():
            return False
        now = self.clock()
        remaining = min(self.idle_seconds, self.born + self.lifetime_seconds - now)
        if remaining <= 0:
            return False
        self.idle, self.expires = wire, now + remaining
        def expire():
            with self.lock:
                if self.idle is wire and self.timer is scheduled:
                    self.discard()
        scheduled = self.timer_factory(remaining, expire)
        self.timer = scheduled
        scheduled.daemon = True
        scheduled.start()
        return True

    def close(self):
        self.closed.set()
        # Shutdown/credential rotation must not wait for an in-flight body.
        # keep() will close it on return instead of caching it.
        if self.lock.acquire(blocking=False):
            try:
                self.discard()
            finally:
                self.lock.release()
