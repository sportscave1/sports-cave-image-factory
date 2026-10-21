"""Read-only handoff to the existing Edition Ops workspace."""
from urllib.parse import urlencode


def destination(row, connect):
    from product_upload_compact import context_from_row
    context = context_from_row(row)
    pid = str(context.get('shopify_product_id') or '')
    title = str(context.get('existing_product_title') or row['data'].get('product_title') or context.get('customer_facing_title')
                or context.get('product_name') or context.get('design_name') or '')
    # Saved identity wins; otherwise use the exact upload correlation tag in
    # the local catalogue. Never call Shopify, move a file or claim a hold.
    from product_upload_identity import tag
    with connect() as conn, conn.cursor() as cur:
        if pid:
            pid = 'gid://shopify/Product/' + pid.rsplit('/', 1)[-1]
        else:
            cur.execute("""SELECT shopify_product_id,title FROM shopify_products
                WHERE COALESCE(raw->'tags',raw_json->'tags','[]'::jsonb) ? %s""", (tag(row['id']),))
            candidates = cur.fetchall()
            if len(candidates) == 1:
                pid, title = candidates[0]['shopify_product_id'], candidates[0]['title']
        cur.execute("""SELECT product_title FROM edition_products
            WHERE shopify_product_gid=%s OR shopify_product_id=ANY(%s)""",
            (pid, [pid, pid.rsplit('/', 1)[-1]]))
        found = cur.fetchall() if pid else []
    return dict(url='/?' + urlencode(dict(page='edition_ops', edition_upload='1', edition_product=pid, edition_search=title)),
                state='Available in Edition Ops' if len(found) == 1 else 'Pending / not found in Edition Ops',
                reason='Use Add / Attach PSD in Edition Ops.' if len(found) == 1 else
                'The product has not been found in Edition Ops yet. Automatic sync may still be pending. No PSD was attached.')


def selection(rows, product_id='', title=''):
    """Stable identity takes precedence; a title is only a search hint."""
    if product_id:
        number = str(product_id).rsplit('/', 1)[-1]
        return [r for r in rows if any(str(r.get(k) or '').rsplit('/', 1)[-1] == number
                for k in ('shopify_product_id', 'shopify_product_gid'))]
    query = str(title).strip().casefold()
    return [r for r in rows if query and query in str(r.get('product_title') or '').casefold()]
