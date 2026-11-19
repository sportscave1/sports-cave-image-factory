"""Read-only inputs for owner-requested prompt trials; never create queue jobs."""
from pathlib import PurePosixPath


def database_choices(workflow, connect=None, *, handle=None):
    if connect is None:
        from supabase_backend import read_connection
        connect = read_connection
    with connect() as conn, conn.cursor() as cur:
        if workflow == 'New design':
            cur.execute("SELECT value FROM app_settings WHERE key=%s", ('home_sports_morning_brief',))
            saved = cur.fetchone()
            edition = (saved or {}).get('value') or {}
            rows = edition.get('design_recommendations', edition.get('recommendations', []) + edition.get('legends', []))
            return [dict(id=str(i), title=r['title'], context=r, source='Home brief ' + str(edition.get('date', ''))) for i, r in enumerate(rows) if r.get('title')]
        if workflow == 'Refresh':
            cur.execute("SELECT key,value FROM app_settings WHERE key = ANY(%s)", (['home_design_refresh', 'home_refresh_manual_products', 'home_refresh_initial_products'],))
            settings = {r['key']: r['value'] for r in cur.fetchall()}
            candidates = (settings.get('home_design_refresh') or {}).get('candidates', [])
            ids = list(set(settings.get('home_refresh_manual_products') or []) | set(settings.get('home_refresh_initial_products') or []))
        else:
            candidates, ids = [], []
        cur.execute("""SELECT shopify_product_id, title, handle, image_url, featured_image_url,
            COALESCE(to_jsonb(p)->>'body_html', to_jsonb(p)->'raw'->>'descriptionHtml',
                     to_jsonb(p)->'raw'->>'body_html') AS description,
            to_jsonb(p)->'tags' AS tags, to_jsonb(p)->>'product_type' AS product_type FROM shopify_products p
            WHERE lower(to_jsonb(p)->>'status')='active'
            AND (%s::text IS NULL OR handle=%s) ORDER BY lower(title), shopify_product_id LIMIT 10001""", (handle, handle))
        products = cur.fetchall()
        if len(products) > 10000:
            raise ValueError('Product catalogue is too large. Narrow the test catalogue before continuing.')
    if workflow == 'Refresh':
        by_id = {str(r['shopify_product_id']).removeprefix('gid://shopify/Product/'): r for r in products}
        chosen = {str(r['product_id']): {**by_id.get(str(r['product_id']), {}), **r} for r in candidates}
        for pid in ids:
            pid = str(pid).removeprefix('gid://shopify/Product/')
            if pid in by_id and pid not in chosen:
                chosen[pid] = by_id[pid]
        products = list(chosen.values())
    return [dict(id=str(r.get('shopify_product_id') or r.get('product_id')), title=r['title'],
                 context=dict(r), source='Refresh suggestions' if workflow == 'Refresh' else 'Product catalogue')
            for r in products if r.get('title')]


def design_choices(provider=None):
    if provider is None:
        from product_upload_services import Dropbox
        provider = Dropbox()
    from product_upload_dropbox import REVIEW, approved, within
    from design_review_metadata import is_working_file, is_refresh_staging
    rows, cursor, seen = [], '', set()
    while True:
        page = provider.api.list_folder_page(provider.token, REVIEW, cursor=cursor, limit=500)
        for entry in page['entries']:
            if (approved(entry) and within(entry.get('path_display', ''), REVIEW) and entry.get('rev')
                    and (not is_working_file(entry['name']) or is_refresh_staging(entry['name']))):
                rows.append(dict(id=entry['id'] + ':' + entry['rev'], title=PurePosixPath(entry['name']).stem,
                                 context=entry, source='Design Studio'))
        if not page.get('has_more'):
            break
        cursor = page.get('cursor')
        if not cursor or cursor in seen:
            raise ValueError('Design Studio list could not be completed. Reload test inputs.')
        seen.add(cursor)
    return sorted(rows, key=lambda r: r['title'].casefold())


def edition_choices(connect=None):
    """Edition Ops product names and URLs only; no sync or edition mutation."""
    if connect is None:
        from supabase_backend import read_connection
        connect = read_connection
    with connect() as conn, conn.cursor() as cur:
        cur.execute("""SELECT DISTINCT ON (btrim(shopify_handle))
            btrim(shopify_handle) AS handle, product_title AS title
            FROM edition_products
            WHERE NULLIF(btrim(shopify_handle), '') IS NOT NULL
              AND NULLIF(btrim(product_title), '') IS NOT NULL
            ORDER BY btrim(shopify_handle), product_title LIMIT 10001""")
        rows = cur.fetchall()
    if len(rows) > 10000:
        raise ValueError('Edition Ops catalogue is too large for this picker.')
    return [dict(id=r['handle'], title=r['title'], source='Edition Ops',
                 context={'product_url': 'https://www.sportscaveshop.com/products/' + r['handle']})
            for r in sorted(rows, key=lambda row: (row['title'].casefold(), row['handle']))]


def load_choices(workflow):
    if workflow == 'Ads':
        return edition_choices()
    return design_choices() if workflow in ('Edit design', 'Upload') else database_choices(workflow)
