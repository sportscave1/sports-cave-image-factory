"""Read-only diagnostics for private Email storage; no mailbox contents queried."""
TABLES = ('support_email_inbox_snapshot', 'customer_support_threads',
          'customer_support_email_settings', 'customer_support_email_preferences')


def schema_issues(cur):
    issues = []
    for table in TABLES:
        cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(%s)", ('public.' + table,))
        row = cur.fetchone()
        if not row:
            issues.append('missing table: ' + table)
            continue
        if not row['relrowsecurity']:issues.append('RLS disabled: ' + table)
        cur.execute("""SELECT count(*) AS count FROM pg_index
            WHERE indrelid=to_regclass(%s) AND indisprimary""", ('public.' + table,))
        if not cur.fetchone()['count']:issues.append('missing primary index: ' + table)
        for role in ('anon', 'authenticated'):
            cur.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE') AS allowed", (role, 'public.' + table))
            if cur.fetchone()['allowed']:issues.append('unsafe client grant: ' + table + ':' + role)
        cur.execute("SELECT has_table_privilege(current_user,%s,'SELECT') AND has_table_privilege(current_user,%s,'INSERT,UPDATE') AS allowed", ('public.' + table, 'public.' + table))
        if not cur.fetchone()['allowed']:issues.append('server access missing: ' + table)
    cur.execute("SELECT to_regclass('public.app_sync_state') AS name")
    if not cur.fetchone()['name']:issues.append('missing existing IDLE coordination table: app_sync_state')
    cur.execute("""SELECT column_name,data_type,is_nullable FROM information_schema.columns
        WHERE table_schema='public' AND table_name='support_email_inbox_snapshot'""")
    columns = {r['column_name']: (r['data_type'], r['is_nullable']) for r in cur.fetchall()}
    for name, kind in (('mailbox_key', 'text'), ('snapshot', 'jsonb'), ('updated_at', 'timestamp with time zone')):
        if columns.get(name) != (kind, 'NO'):issues.append('incompatible snapshot column: ' + name)
    cur.execute("""SELECT pg_get_constraintdef(oid) AS definition FROM pg_constraint
        WHERE conrelid=to_regclass('public.support_email_inbox_snapshot') AND contype='c'""")
    if not any('524288' in r['definition'] and 'octet_length' in r['definition'] for r in cur.fetchall()):
        issues.append('missing snapshot size constraint')
    return issues
