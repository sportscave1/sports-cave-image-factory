"""Controlled local profile: 1,000 synthetic customers, 80ms/request; no external I/O.
Run with the disposable tests/crm_postgres_server.mjs process already running.
"""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import threading
import time
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from tests.test_crm_ui import SCRIPT
from tests.crm_fixtures import ShopifyFixture
from crm_campaign_store import CampaignStore
from crm_segment_counts import SegmentCounts
import crm_campaign_markets as markets
import crm_preview_cache as preview

stats={};lock=threading.Lock()
def timed(name,fn):
    def call(*a,**k):
        start=time.perf_counter()
        try:return fn(*a,**k)
        finally:
            with lock:
                row=stats.setdefault(name,{'seconds':0,'calls':0})
                row['seconds']+=time.perf_counter()-start;row['calls']+=1
    return call
original=ShopifyFixture.__call__
def wire(self,doc,v):
    time.sleep(.08)
    return original(self,doc,v)
cache=SegmentCounts(loader=timed('counts',markets.calculate))
with (patch('crm_segment_counts.COUNTS',cache),patch.object(ShopifyFixture,'__call__',timed('shopify',wire)),
      patch.object(markets,'country',timed('country',markets.country)),patch.object(markets,'eligibility',timed('eligibility',markets.eligibility)),
      patch.object(CampaignStore,'active_suppression_hashes',timed('suppression',CampaignStore.active_suppression_hashes)),
      patch.object(CampaignStore,'list_drafts',timed('draft_list',CampaignStore.list_drafts)),
      patch.object(CampaignStore,'draft',timed('draft_load',CampaignStore.draft)),
      patch.object(CampaignStore,'email_defaults',timed('email_defaults',CampaignStore.email_defaults)),
      patch.object(CampaignStore,'html_library',timed('template_library',CampaignStore.html_library)),
      patch.object(preview,'render_campaign',timed('preview',preview.render_campaign))):
    at=AppTest.from_string(SCRIPT.replace('ShopifyFixture()','ShopifyFixture(1000)'));at.session_state['route']='CRM Campaigns'
    start=time.perf_counter();at.run(timeout=30);stats['initial_render_seconds']=time.perf_counter()-start
    stats['exceptions']=[e.message for e in at.exception]
    cache.executor.shutdown(wait=True)
    calls=stats.get('shopify',{}).get('calls',0)
    start=time.perf_counter();at.run(timeout=30);stats['cached_render_seconds']=time.perf_counter()-start
    stats['cached_render_shopify_calls']=stats.get('shopify',{}).get('calls',0)-calls
    stats['draft_load']=stats.get('draft_load',{'seconds':0,'calls':0})
    stats['template_library']=stats.get('template_library',{'seconds':0,'calls':0})
    shop=__import__('crm_shopify').Shopify(at.session_state['wire'])
    start=time.perf_counter();cache.display(shop,CampaignStore(__import__('tests.crm_db_fixture',fromlist=['connect']).connect));stats['cached_count_lookup_seconds']=time.perf_counter()-start
print(json.dumps(stats,indent=2))
Path('tests/fixtures/segment-profile-after.json').write_text(json.dumps(stats,indent=2)+'\n',encoding='utf-8')
