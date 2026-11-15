"""Release stale cache aliases only after scoped authoritative deletion checks."""
import json
import shopify_sync as shopify

QUERY = '''query VerifyCacheOwner($old:ID!, $current:ID!) {
  shop { myshopifyDomain }
  currentAppInstallation { accessScopes { handle } }
  previous: product(id:$old) { id }
  current: product(id:$current) { id handle }
}'''


def reconcile(connect, product, config=None):
    config = config or shopify.get_config()
    domain = shopify.normalize_store_domain(config.get('store_domain'))
    if not domain:
        raise ValueError('The Shopify shop must be configured before identity reconciliation.')
    pid, handle = product['shopify_product_id'], product.get('handle')
    with connect() as conn, conn.cursor() as cur:
        cur.execute('SELECT * FROM shopify_products WHERE handle=%s', (handle,))
        old = cur.fetchone()
    if not old or str(old['shopify_product_id']) in (pid, pid.rsplit('/',1)[-1]):
        return False
    old_id = str(old['shopify_product_id'])
    gid = old_id if old_id.startswith('gid://shopify/Product/') else 'gid://shopify/Product/'+old_id
    data, _ = shopify.graphql_request(QUERY, variables={'old':gid,'current':pid}, config=config)
    scopes = {s['handle'] for s in (data.get('currentAppInstallation') or {}).get('accessScopes',[])}
    if ((data.get('shop') or {}).get('myshopifyDomain') != domain or 'read_products' not in scopes
            or data.get('current') != {'id':pid,'handle':handle} or 'previous' not in data):
        raise ValueError('Shopify identity/access could not be verified. Cached ownership was preserved.')
    if data['previous'] is not None:
        raise ValueError('The prior cache owner still exists in Shopify. Resolve the identity conflict before mapping.')
    # API errors are raised by graphql_request. Null is accepted only with valid
    # read_products access and a matching known current product in the same shop.
    with connect() as conn, conn.cursor() as cur:
        cur.execute('LOCK TABLE shopify_products IN SHARE ROW EXCLUSIVE MODE')
        cur.execute('SELECT * FROM shopify_products WHERE handle=%s FOR UPDATE', (handle,))
        current = cur.fetchone()
        if not current:
            return False
        if current['shopify_product_id'] != old_id:
            raise ValueError('Cache ownership changed during reconciliation. Retry the exact product.')
        archive = {'shop':domain,'product_id':gid,'released_handle':handle,'cache':dict(current),
                   'replacement_product_id':pid,'proof':data}
        key='shopify-cache-retired:'+domain+':'+old_id
        cur.execute('''INSERT INTO app_settings(key,value,updated_at) VALUES(%s,%s::jsonb,now())
            ON CONFLICT(key) DO NOTHING''',(key,json.dumps(archive,default=str)))
        # Preserve the row, raw history and every foreign identity. Only this
        # disposable catalogue alias is released; no historical records change.
        cur.execute('UPDATE shopify_products SET handle=NULL WHERE shopify_product_id=%s AND handle=%s', (old_id,handle))
        conn.commit()
    return True
