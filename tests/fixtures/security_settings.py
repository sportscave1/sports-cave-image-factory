import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import streamlit as st
import security_protection_ui as ui
from security_protection import DEFAULTS
class FixtureStore:
    def admin(self,*args):return {'role':'admin','id':'fixture'}
    def q(self,*args,**kwargs):return []
    def reauthenticate(self,*args):pass
    def save_policy(self,*args):pass
ui.STORE=FixtureStore()
ui.cached_policy=lambda:dict(DEFAULTS)
st.set_page_config(layout='wide')
ui.render(st,{'id':'fixture','role':'admin'},'fixture-session')
st.html('<script>'+Path('app-protection.js').read_text().replace('SC_POLICY',__import__('json').dumps(DEFAULTS)).replace('SC_NAME','"Fixture administrator"')+'</script>',unsafe_allow_javascript=True)
