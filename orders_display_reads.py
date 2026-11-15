"""Fresh, bounded Orders display reads; generation/write workflows are untouched."""
from contextlib import contextmanager


def download_links(rows):
    import auto_editions_runtime as runtime
    import supabase_backend as db
    if not runtime.enabled():
        return {}

    def read(cur):
        @contextmanager
        def current_lease():
            # Store readers open their own cursors, exclusively on this request's
            # autocommit lease. No extra checkout, preflight or transaction.
            yield cur.connection
        return runtime.download_links(rows or [], read_connection=current_lease)

    return db._run_read_operation('orders.jpg_status', read)[0]
