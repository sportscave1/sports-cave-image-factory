"""Bound optional Email database failures without caching any mailbox content."""
import logging
import threading
import time

LOGGER = logging.getLogger(__name__)


class DatabaseCooldown:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.until = 0

    def ready(self):
        with self.lock:
            return self.clock() >= self.until

    def failed(self, error, operation):
        with self.lock:
            if self.clock() < self.until:
                return
            missing = getattr(error, 'sqlstate', '') == '42P01' or type(error).__name__ == 'UndefinedTable'
            self.until = self.clock() + (300 if missing else 60)
            LOGGER.warning('email_database operation=%s category=%s type=%s retry_seconds=%d',
                           operation, 'SCHEMA_MISSING' if missing else 'DATABASE',
                           type(error).__name__, 300 if missing else 60)


SNAPSHOT_DB = DatabaseCooldown()
METADATA_DB = DatabaseCooldown()
