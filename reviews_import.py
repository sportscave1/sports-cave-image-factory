"""Bounded offline CSV preview and historical export normalization."""
import csv
import io
from typing import Protocol
from reviews_model import auto_mapping,normalize

class Provider(Protocol):
    def page(self,page:int)->list:...
    def normalize(self,row:dict)->dict:...

def read_csv(data):
    if len(data)>10*1024*1024:raise ValueError('Upload a CSV smaller than 10 MB.')
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError:raise ValueError('Use a UTF-8 CSV file.') from None
    if '\x00' in text:raise ValueError('Invalid CSV data.')
    try:
        dialect=csv.Sniffer().sniff(text[:8192],delimiters=',;\t')
    except csv.Error:dialect=csv.excel
    reader=csv.DictReader(io.StringIO(text),dialect=dialect)
    headers=reader.fieldnames or []
    if not headers or len(headers)>50 or len(set(headers))!=len(headers):raise ValueError('Use unique CSV column headings (at most 50).')
    rows=[]
    try:
        for row in reader:
            if len(rows)>=10000:raise ValueError('Import at most 10,000 rows per file.')
            if None in row:raise ValueError('CSV row has too many columns.')
            rows.append(row)
    except csv.Error:raise ValueError('Malformed CSV.') from None
    return headers,rows

def preview(rows,mapping,store,source='csv',source_store='',published_only=False):
    items=[];invalid=[];duplicates=0;unresolved=0;skipped=0;seen=set()
    for i,raw in enumerate(rows,2):
        try:
            item=normalize(raw,source,mapping,source_store)
            if published_only and item['status']!='PUBLISHED':skipped+=1;continue
            identity=item.get('source_fingerprint') or item['dedupe_key']
            if identity in seen:duplicates+=1;continue
            seen.add(identity)
            items.append(item)
        except (ValueError,TypeError):invalid.append({'row':i,'reason':'Invalid rating, date or review text'})
    # One bounded identity query per batch, never one per review.
    existing=set()
    for start in range(0,len(items),200):
        batch=items[start:start+200]
        keys=[r['dedupe_key'] for r in batch]
        unresolved+=sum(p is None and r['review_type']=='PRODUCT' for r,p in zip(batch,store.match_products([r['product_hints'] for r in batch])))
        fingerprints=[r['source_fingerprint'] for r in batch if r.get('source_fingerprint')]
        found=store.q('SELECT dedupe_key,source_fingerprint FROM sc_reviews WHERE dedupe_key=ANY(%s::text[]) OR source_fingerprint=ANY(%s::text[])',(keys,fingerprints))
        found_keys={r['dedupe_key'] for r in found};found_fingerprints={r.get('source_fingerprint') for r in found}-{None}
        existing.update(r['dedupe_key'] for r in batch if r['dedupe_key'] in found_keys or r.get('source_fingerprint') in found_fingerprints)
    duplicates+=sum(i['dedupe_key'] in existing for i in items)
    return {'items':items,'ready':len(items)-len(existing),'duplicates':duplicates,'unresolved':unresolved,'invalid':invalid,'skipped':skipped,'media':sum(len(i['media']) for i in items)}

class LegacyExport:
    """Offline normalization for historical exports; no credentials or network API."""
    def __init__(self, env=None):
        self.shop=(env or {}).get('SHOPIFY_STORE_DOMAIN','').strip().lower()
    def normalize(self,row):
        reviewer=row.get('reviewer') or {}
        # Judge.me internal product_id is NOT a Shopify product ID.
        raw={**row,'source_review_id':row.get('id'),'product_id':row.get('product_external_id',''),
          'reviewer_name':reviewer.get('name') or row.get('reviewer_name',''),
          'email':reviewer.get('email',''),'source_verified':row.get('verified',False),
          'status':'ARCHIVED' if row.get('archived') or row.get('hidden') is True else 'PUBLISHED' if row.get('hidden') is False and row.get('curated','ok')=='ok' else 'PENDING',
          'review_type':'product' if row.get('product_id') or row.get('product_external_id') else 'store',
          'picture_urls':row.get('pictures') or row.get('picture_urls') or [],
          'video_urls':row.get('videos') or row.get('video_urls') or [],'merchant_reply':row.get('reply') or row.get('merchant_reply') or ''}
        item=normalize(raw,'judgeme',source_store=self.shop)
        item['video_export_required']=bool(row.get('has_published_videos'))
        return item
