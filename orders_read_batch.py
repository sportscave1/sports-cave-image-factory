"""Pipeline independent SELECTs on one exclusive, watchdog-protected lease."""
from contextlib import ExitStack


def read_batch(cur, readers):
    pending = {}
    with ExitStack() as stack:
        with cur.connection.pipeline():
            for name, enqueue in readers.items():
                child = stack.enter_context(cur.connection.cursor())
                if enqueue(child):
                    pending[name] = child
        # The pipeline sync confirms every query before any results are merged.
        # An error propagates to the existing whole-read retry/cancel handler.
        rows = {name: child.fetchall() for name, child in pending.items()}
    return {'rows': rows, 'executed': set(pending)}
