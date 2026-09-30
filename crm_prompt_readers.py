"""Small public-context reads for the campaign prompt; never writes edition data."""
import json
from crm_catalogue import product_id, product_url, edition_for
from crm_picker_cache import load

COLLECTION_PAGE = '''query CampaignPromptCollections($query:String,$after:String) {
 collections(first:8,query:$query,after:$after,sortKey:TITLE) {
 nodes { id title description handle }
 pageInfo { hasNextPage endCursor } }
 shop { primaryDomain { url } } }'''


class PromptReader:
    def __init__(self, shop, edition_reader=None):
        self.shop=shop
        if edition_reader is None:
            from supabase_backend import list_edition_products_read_only
            edition_reader=list_edition_products_read_only
        self.editions=edition_reader

    def products(self, query='', offset=0):
        def fetch():
            rows=self.editions(search=query,limit=9,offset=offset)
            return {'rows':[{'id':product_id(r.get('shopify_product_gid') or r.get('shopify_product_id')),
                             'title':r.get('product_title',''),'handle':r.get('shopify_handle','')}
                            for r in rows[:8]],'more':len(rows)>8}
        return load(('campaign-prompt-products',self.shop.namespace,query,offset),fetch)[0]

    def collections(self, query='', after=None):
        # Same authorised Shopify transport as Catalogue.collections, bounded
        # cursor pages instead of loading the entire collection list on open.
        term='title:'+json.dumps(query.strip()[:150]) if query.strip() else None
        data=self.shop.query(COLLECTION_PAGE,{'query':term,'after':after},'prompt collections',600)
        page=data['collections']
        domain=product_url(((data.get('shop') or {}).get('primaryDomain') or {}).get('url','')).rstrip('/')
        for row in page['nodes']:
            if domain and row.get('handle'):
                from urllib.parse import quote
                row['onlineStoreUrl']=domain+'/collections/'+quote(row['handle'],safe='')
        return {'rows':page['nodes'],'more':page['pageInfo']['hasNextPage'],'cursor':page['pageInfo']['endCursor']}

    def product(self, identity):
        from crm_campaign_prompt import clean
        nodes=self.shop.products([identity],fresh=True,public_context=True)
        row=next((p for p in nodes if p.get('id')==identity),None)
        if not row:raise ValueError('Edition is no longer available. Select it again.')
        facts={'kind':'Single product','source':'Shopify public product','id':identity,
               'title':clean(row['title'],300),'url':product_url(row.get('onlineStoreUrl','')),
               'sport_or_product_type':clean(row.get('productType',''),100),
               'story':clean(row.get('description',''),800)}
        # Only explicit public taxonomy tags; never infer identity from a title.
        for label in ('sport','athlete','team'):
            values=[clean(t.split(':',1)[1],100) for t in row.get('tags',[]) if t.casefold().startswith(label+':')]
            if values:facts[label]=', '.join(values)[:200]
        return facts

    def availability(self, identity):
        rows=self.editions(product_ids=[identity],limit=10)
        value=edition_for({'id':identity,'handle':''},rows)
        if value is None:raise ValueError('Edition availability cannot be verified. Retry or change email type.')
        # No cursor/inventory arithmetic. Use the existing ledger projection and
        # the existing Edition Ops status thresholds without copying numbers.
        from edition_ops import _widget_status
        return {'size':value['limit'],'remaining':value['remaining'],
                'status':_widget_status(value['remaining']),'source':'Edition Ops read-only ledger'}

    def belongs(self, product, collection):
        cursor=None;seen=set()
        while True:
            page=self.shop.collections(product,after=cursor,fresh=True)
            if any(r['id']==collection for r in page['nodes']):return True
            if not page['pageInfo'].get('hasNextPage'):return False
            cursor=page['pageInfo'].get('endCursor')
            if not cursor or cursor in seen:raise ValueError('Collection membership unavailable. Retry.')
            seen.add(cursor)
