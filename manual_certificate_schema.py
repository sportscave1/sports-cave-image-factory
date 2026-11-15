"""Read-only schema contract shared by deployment and certificate controls."""

REQUIRED_COLUMNS = {
    'manual_order_line_editions': {'id', 'source_channel', 'external_order_id',
        'external_line_item_id', 'canonical_product_gid', 'edition_number', 'edition_total',
        'reason', 'created_by_user_id', 'created_at', 'verified_at', 'duplicate_confirmed'},
    'manual_certificate_audit': {'id', 'manual_id', 'action', 'actor_id',
        'old_value', 'new_value', 'occurred_at'},
}
REQUIRED_TRIGGERS = {
    'manual_order_line_editions_insert_guard': ('manual_order_line_editions', 'enforce_manual_order_line_edition_insert', 23),
    'manual_certificate_remove_guard': ('manual_order_line_editions', 'guard_manual_certificate_removal', 11),
    'manual_certificate_audit_changes': ('manual_order_line_editions', 'audit_manual_certificate_change', 29),
    'manual_certificate_audit_immutable': ('manual_certificate_audit', 'enforce_manual_order_line_edition_immutability', 27),
}
IDENTITY_INDEX = 'manual_certificate_canonical_line_unique'


def schema_issues(cur, *, include_identity=True):
    """Inspect actual catalogues, not a filename marker or cached UI state."""
    issues = []
    cur.execute("""SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns
                   WHERE table_schema='public' AND table_name=ANY(%s)""", (list(REQUIRED_COLUMNS),))
    columns = {(r['table_name'], r['column_name']): r for r in cur.fetchall()}
    for table, required in REQUIRED_COLUMNS.items():
        for column in sorted(required):
            if (table, column) not in columns:
                issues.append(f'missing column: {table}.{column}')
    duplicate = columns.get(('manual_order_line_editions', 'duplicate_confirmed'))
    if duplicate and (duplicate['data_type'] != 'boolean' or duplicate['is_nullable'] != 'NO'):
        issues.append('invalid duplicate_confirmed: expected non-null boolean')
    cur.execute("""SELECT t.tgname, c.relname, p.proname, t.tgenabled, t.tgtype
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_proc p ON p.oid=t.tgfoid
        WHERE n.nspname='public' AND NOT t.tgisinternal AND c.relname=ANY(%s)""", (list(REQUIRED_COLUMNS),))
    triggers = {r['tgname']: r for r in cur.fetchall()}
    for name, (table, function, events) in REQUIRED_TRIGGERS.items():
        actual = triggers.get(name, {})
        if (actual.get('relname'), actual.get('proname'), actual.get('tgtype')) != (table, function, events) or actual.get('tgenabled') not in ('O', 'A'):
            issues.append(f'missing/incompatible trigger: {table}.{name}')
    cur.execute("""SELECT p.proname, p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.pronargs=0 AND p.proname=ANY(%s)""",
        ([v[1] for v in REQUIRED_TRIGGERS.values()],))
    functions = {r['proname']: r['prosrc'] for r in cur.fetchall()}
    for function in {v[1] for v in REQUIRED_TRIGGERS.values()}:
        if function not in functions:
            issues.append(f'missing function: {function}')
    if 'duplicate_confirmed' not in functions.get('enforce_manual_order_line_edition_insert', ''):
        issues.append('manual certificate guard lacks duplicate confirmation')
    cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass('public.manual_certificate_audit')")
    if not (cur.fetchone() or {}).get('relrowsecurity'):
        issues.append('manual_certificate_audit requires RLS')
    if include_identity:
        cur.execute("""SELECT i.indisunique, i.indisvalid, pg_get_indexdef(i.indexrelid) AS definition
            FROM pg_index i WHERE i.indexrelid=to_regclass(%s)""", ('public.' + IDENTITY_INDEX,))
        index = cur.fetchone() or {}
        if not (index.get('indisunique') and index.get('indisvalid') and
                all(term in index.get('definition', '') for term in
                    ('source_channel', 'external_order_id', 'external_line_item_id', 'regexp_replace'))):
            issues.append(f'missing/incompatible unique index: {IDENTITY_INDEX}')
    return issues
