"""Controlled picker profile. No live services; latency is deliberately injected."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import Mock,patch
from streamlit.testing.v1 import AppTest
from tests.test_crm_modular_catalogue import catalogue_doc,event
from crm_catalogue import Catalogue
from crm_picker_cache import _CACHE
from crm_preview_cache import preview
from crm_campaign_content import settings
import crm_section_ui
_CACHE.invalidate();calls={'index':0,'collections':0,'facts':0}
facts=catalogue_doc()['middle_sections'][-1]['products']
def transport(query,variables,*args):
 calls['collections']+=1;time.sleep(.08)
 return {'collections':{'nodes':[{'id':'gid://shopify/Collection/1','title':'Motorsport'}],'pageInfo':{'hasNextPage':False,'endCursor':None}}}
cat=Catalogue(Mock(namespace='profile',query=transport))
def index(*args):
 calls['index']+=1;time.sleep(.08);return {'rows':facts,'more':False}
cat._index_search=index
def resolve(ids,*a,**kw):calls['facts']+=1;time.sleep(.16);return [p for p in facts if p['id'] in ids]
cat.resolve=resolve;crm_section_ui._profile_cat=cat
script="""import streamlit as st
from tests.test_crm_modular_catalogue import catalogue_doc
from crm_section_ui import product_picker,_profile_cat
st.session_state.setdefault('doc',catalogue_doc())
st.session_state.setdefault('p_generation','test')
product_picker(st.session_state.doc,st.session_state.doc['middle_sections'][-1]['id'],_profile_cat,'p_')
"""
result={}
def measure(label,fn):
 before=dict(calls);start=time.perf_counter();fn();result[label+'_s']=time.perf_counter()-start
 result[label+'_calls']={k:calls[k]-before[k] for k in calls}
at=AppTest.from_string(script)
measure('open',lambda:at.run())
measure('search',lambda:at.text_input[0].set_value('art').run())
measure('selection',lambda:at.checkbox[1].uncheck().run())
measure('cached_reopen',lambda:AppTest.from_string(script).run())
doc=catalogue_doc();state={};preview(state,doc,settings())
for field in ('price','limit','remaining'):
 cfg=dict(doc['middle_sections'][-1]['settings']);cfg['display']=dict(cfg['display']);cfg['display'][field]=not cfg['display'][field]
 def toggle():event(doc,'settings',id=doc['middle_sections'][-1]['id'],settings=cfg);preview(state,doc,settings())
 measure(field+'_render',toggle)
result['exceptions']=[e.message for e in at.exception]
Path('tests/fixtures/catalogue-picker-after.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
