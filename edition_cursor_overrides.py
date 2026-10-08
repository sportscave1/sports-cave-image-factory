"""Explicit administrator numbering changes; never mutate historical allocations."""
import supabase_backend as backend
import edition_versions


def save(handle, *, run_id, expected_next, next_number, request_id, actor_id, acknowledged=False):
    with backend.connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT override_edition_cursor(%s,%s,%s,%s,%s,%s,%s) AS result',
                    (handle, run_id, expected_next, next_number, request_id, actor_id, acknowledged))
        result = cur.fetchone()['result']
    # Durable Pending state is committed before this in-process accelerator.
    edition_versions.kick(handle)
    return result
