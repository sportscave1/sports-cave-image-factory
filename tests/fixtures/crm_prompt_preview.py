"""Real Campaigns fixture with fabricated prompt catalogue; no external I/O."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import runpy
import streamlit as st
from unittest.mock import patch
from tests.test_crm_prompt_helper import Reader,PRODUCT

class FixtureReader(Reader):
    def __init__(self,*args,**kwargs):super().__init__()
    def products(self,query='',offset=0):return {'rows':[PRODUCT] if 'none' not in query else [],'more':False}
    def collections(self,query='',after=None):
        if 'offline' in query:raise RuntimeError('Fixture offline')
        return {'rows':[{'id':'gid://shopify/Collection/'+('2' if after else '1'),'title':'Motorsport heroes' if after else 'Football legends','description':'Artwork celebrating memorable sporting moments.','onlineStoreUrl':'https://www.sportscaveshop.com/collections/football'}], 'more':not after,'cursor':'page2' if not after else 'end'}

@st.cache_resource
def install():
    p=patch('crm_prompt_readers.PromptReader',FixtureReader);p.start();return p
install()
runpy.run_path(str(Path(__file__).with_name('crm_production_v2_preview.py')),run_name='__main__')
