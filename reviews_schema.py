"""Read-only deployment verification; no lazy schema creation."""
COLUMNS={'sc_reviews':('id','source','source_review_id','product_id','rating','title','body','status','verified_purchase','source_verified','dedupe_key','search_document','moderated_at','order_id','customer_id'),
 'sc_review_totals':('scope','total','rating_total','fives','attention','published','published_rating'),
 'sc_review_days':('day','total'),'sc_review_settings':('key','value'),
 'sc_review_imports':('id','status','payload','cursor','lease_until','attempts','imported','duplicates','invalid'),
 'sc_review_tokens':('token_hash','expires_at','order_id','customer_id','product_id','review_id'),
 'sc_review_audit':('id','review_id','actor','action')}
INDEXES=('sc_reviews_source','sc_reviews_page','sc_reviews_product_page','sc_reviews_search','sc_review_import_due')

def schema_issues(cur):
    cur.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=ANY(%s)",(list(COLUMNS),))
    found={}
    for r in cur.fetchall():found.setdefault(r['table_name'],set()).add(r['column_name'])
    issues=['missing public.'+t+'.'+c for t,cols in COLUMNS.items() for c in cols if c not in found.get(t,set())]
    cur.execute("SELECT relname,relrowsecurity FROM pg_class WHERE relname=ANY(%s) AND relnamespace='public'::regnamespace",(list(COLUMNS),))
    issues+=['RLS disabled: public.'+r['relname'] for r in cur.fetchall() if not r['relrowsecurity']]
    cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexname=ANY(%s)",(list(INDEXES),))
    names={r['indexname'] for r in cur.fetchall()};issues+=['missing index '+i for i in INDEXES if i not in names]
    cur.execute("SELECT tgname FROM pg_trigger WHERE tgname='sc_review_aggregate_change' AND NOT tgisinternal AND tgenabled<>'D'")
    if not cur.fetchall():issues.append('missing enabled review aggregate trigger')
    return issues
