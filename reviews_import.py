"""Bounded CSV preview and explicit official provider adapter; no dashboard scraping."""
import csv
import io
import os
import re
from typing import Protocol
import requests
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

def preview(rows,mapping,store,source='csv',source_store=''):
    items=[];invalid=[];duplicates=0;unresolved=0;seen=set()
    for i,raw in enumerate(rows,2):
        try:
            item=normalize(raw,source,mapping,source_store)
            if item['dedupe_key'] in seen:duplicates+=1;continue
            seen.add(item['dedupe_key'])
            items.append(item)
        except (ValueError,TypeError):invalid.append({'row':i,'reason':'Invalid rating, date or review text'})
    # One bounded identity query per batch, never one per review.
    existing=set()
    for start in range(0,len(items),200):
        batch=items[start:start+200]
        keys=[r['dedupe_key'] for r in batch]
        unresolved+=sum(p is None for p in store.match_products([r['product_hints'] for r in batch]))
        existing.update(r['dedupe_key'] for r in store.q('SELECT dedupe_key FROM sc_reviews WHERE dedupe_key=ANY(%s::text[])',(keys,)))
    duplicates+=sum(i['dedupe_key'] in existing for i in items)
    return {'items':items,'ready':len(items)-len(existing),'duplicates':duplicates,'unresolved':unresolved,'invalid':invalid}

class JudgeMe:
    """Official server-side GET only. Reply syncing is not supported by list API."""
    def __init__(self,env=None,session=None):
        env=os.environ if env is None else env
        self.token=env.get('JUDGEME_PRIVATE_API_TOKEN','').strip()
        self.shop=env.get('SHOPIFY_STORE_DOMAIN','').strip().lower()
        self.session=session or requests.Session()
    @property
    def configured(self):return bool(self.token and re.fullmatch(r'[a-z0-9][a-z0-9-]*\.myshopify\.com',self.shop))
    def page(self,page):
        if not self.configured:raise ValueError('Judge.me server credentials are not configured.')
        try:
            response=self.session.get('https://api.judge.me/api/v1/reviews',params={'api_token':self.token,'shop_domain':self.shop,'per_page':100,'page':int(page)},timeout=(3,10),allow_redirects=False)
            if response.status_code!=200:raise ValueError()
            data=response.json();rows=data['reviews']
            if not isinstance(rows,list) or len(rows)>100:raise ValueError()
            return rows
        except Exception:raise RuntimeError('Judge.me could not return a valid review page.') from None
    def normalize(self,row):
        reviewer=row.get('reviewer') or {}
        # Judge.me internal product_id is NOT a Shopify product ID.
        raw={**row,'source_review_id':row.get('id'),'product_id':row.get('product_external_id',''),
          'reviewer_name':reviewer.get('name') or row.get('reviewer_name',''),
          'email':reviewer.get('email',''),'source_verified':row.get('verified',False),
          'status':'PUBLISHED' if row.get('hidden') is False else 'PENDING','merchant_reply':''}
        return normalize(raw,'judgeme',source_store=self.shop)
