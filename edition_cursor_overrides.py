"""Explicit administrator numbering changes; never mutate historical allocations."""
import supabase_backend as backend
import edition_versions

SIGNATURE='public.override_edition_cursor(text,uuid,integer,integer,uuid,uuid,integer,integer)'


class SchemaUnavailable(RuntimeError):pass


def schema_issues(cur):
    cur.execute('SELECT to_regprocedure(%s)::text AS signature',(SIGNATURE,))
    return [] if (cur.fetchone() or {}).get('signature') else ['Edition Ops database upgrade required. Run the reviewed edition migration chain before saving. Your edits have been retained.']


def require_schema():
    with backend.connect() as conn, conn.cursor() as cur:
        issues=schema_issues(cur)
    if issues:raise SchemaUnavailable(issues[0])


def save(handle, *, run_id, expected_next, next_number, request_id, actor_id, acknowledged=False,expected_limit=None,edition_limit=None):
    with backend.connect() as conn, conn.cursor() as cur:
        if expected_limit is None:
            cur.execute('SELECT edition_total FROM edition_products WHERE shopify_handle=%s',(handle,))
            expected_limit=cur.fetchone()['edition_total']
        cur.execute('SELECT public.override_edition_cursor(%s::text,%s::uuid,%s::integer,%s::integer,%s::uuid,%s::uuid,%s::integer,%s::integer) AS result',
                    (handle, run_id, expected_next, next_number, request_id, actor_id, expected_limit,edition_limit if edition_limit is not None else expected_limit))
        result = cur.fetchone()['result']
    # Durable Pending state is committed before this in-process accelerator.
    try:edition_versions.kick(handle)
    except Exception:
        # The database job is durable. Accelerator failure must not lose a
        # confirmed save or cause a new request identity on retry.
        import logging
        logging.getLogger(__name__).exception('Edition sync accelerator unavailable')
    return result
