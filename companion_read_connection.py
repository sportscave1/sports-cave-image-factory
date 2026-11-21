"""Dedicated short-lived status connections; never wrap job/control writes."""
from contextlib import contextmanager
from threading import Timer

@contextmanager
def read_connection(factory):
    with factory() as conn:
        # Existing factory has an 8s connect timeout. A client cancel also covers
        # pool-side query waits, which a server statement_timeout cannot cover.
        def cancel():
            try:
                if hasattr(conn, 'cancel'): conn.cancel()
            except Exception:
                pass
        watchdog = Timer(3, cancel)
        watchdog.daemon = True
        watchdog.start()
        try:
            with conn.cursor() as cur:
                cur.execute('SET LOCAL statement_timeout = 2500')
                cur.execute('SET LOCAL lock_timeout = 500')
            yield conn
        finally:
            watchdog.cancel()
