"""Restricted SC3284 pilot. TEST output is never supplier approval or a fulfilment action."""
PRODUCT='gid://shopify/Product/10465710768435'
ORDER='gid://shopify/Order/18941430858035'
LINE='50792075133235'
FILE='id:u1tYiAa2O-AAAAAAAAAj1g'
REVISION='0165da1c7a2ee4d000000036d367e13'
CONTENT_HASH='f1e90d6ef5f8f6083a0577c3846aec472050283c126a5a30cc8ccae4aa799c56'


def eligible(row, mapping):
    import psd_directory
    return bool(mapping and mapping.get('verified') is True and mapping.get('dropbox_file_id')==FILE
                and psd_directory.product_id(row)==PRODUCT and str(row.get('shopify_order_id'))==ORDER
                and str(row.get('shopify_line_item_id')).removeprefix('gid://shopify/LineItem/')==LINE
                and (row.get('allocation_index') or row.get('unit_ordinal'))==1
                and row.get('edition_number')==2 and row.get('edition_total')==100 and not row.get('invalidated_at'))


def confirmed_unit():
    import supabase_backend
    from psd_mapping_store import STORE
    with supabase_backend.connect() as conn,conn.cursor() as cur:
        cur.execute('SELECT * FROM edition_orders WHERE id=%s',(655,));row=cur.fetchone()
    if not row:raise ValueError('The verified SC3284 allocation is unavailable.')
    row=dict(row);mapping=STORE.read().get(PRODUCT)
    if not eligible(row,mapping) or any(row.get(k) is not True for k in ('allocation_valid','identity_enforced')) or row.get('status')!='assigned' or row.get('cancelled_at'):
        raise ValueError('SC3284 allocation or PSD mapping changed. Test generation is blocked.')
    keys=('shopify_product_gid','shopify_order_id','shopify_line_item_id','edition_number','edition_total','unit_ordinal','allocation_index','quantity','allocation_key','allocation_valid','identity_enforced','invalidated_at','status')
    unit={k:row.get(k) for k in keys}
    unit.update(source='read_only_supabase',allocation_id=row['id'],dropbox_file_id=FILE,dropbox_revision=REVISION,content_hash=CONTENT_HASH)
    return unit


def validate_context(context):
    unit=context['unit'];meta=context['metadata']
    if (unit.get('shopify_product_gid')!=PRODUCT or unit.get('shopify_order_id')!=ORDER or str(unit.get('shopify_line_item_id'))!=LINE
        or unit.get('allocation_id')!=655 or unit.get('allocation_index')!=1 or unit.get('edition_number')!=2 or unit.get('edition_total')!=100
        or unit.get('allocation_valid') is not True or unit.get('identity_enforced') is not True or unit.get('invalidated_at') is not None
        or unit.get('status')!='assigned' or meta.get('id')!=FILE or meta.get('rev')!=REVISION or meta.get('content_hash')!=CONTENT_HASH):
        raise ValueError('Pilot unit/file identity does not match the verified proof.')
    return context
