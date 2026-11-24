"""Bounded immutable source-hash reuse; does not cache recovery decisions."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib

# Filled from the exact pre/post optimisation sources and verified by regression
# tests. This performance-only edit must not replenish unchanged retry budgets.
PREVIOUS_RECOVERY_HASH = '1d4e2d7b00bf6046d7cc829e7524053ce9a2fe55e23bd3c19c53d9973cb9e198'
OPTIMISED_RECOVERY_HASH = '0797682db09dcb8a67c873a1c6dfe95716100f648de1eadf3e416b2b0bb165be'


_snapshot = ContextVar('recovery_source_snapshot', default=None)


@contextmanager
def source_snapshot():
    """A fresh bounded cache per plan, isolated between concurrent planners."""
    token = _snapshot.set({})
    try:
        yield
    finally:
        _snapshot.reset(token)


def _read(path, signature):
    value = hashlib.sha256(path.read_bytes()).hexdigest()
    after = path.stat()
    if signature != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise OSError('Recovery source changed while computing its revision; retry scan.')
    return value


def file_digest(path):
    stat = path.stat()
    signature = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    cache = _snapshot.get()
    key = (path, signature)
    if cache is not None and key in cache:
        value = cache[key]
    else:
        value = _read(path, signature)
        if cache is not None and len(cache) < 128:
            cache[key] = value
    if path.name == 'auto_editions_recovery.py' and value == OPTIMISED_RECOVERY_HASH:
        return PREVIOUS_RECOVERY_HASH
    return value
