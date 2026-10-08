"""Safe local visual fixture: actual Mockups renderer, synthetic images, no cloud writes."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import streamlit as st
from PIL import Image, ImageDraw
from unittest.mock import patch
import types
app=types.ModuleType('mockups_fixture_app')
app.__file__=str(Path('app.py').resolve())
exec(compile(Path('app.py').read_text(encoding='utf-8').rsplit('main()',1)[0],app.__file__,'exec'),app.__dict__)
import image_factory
from tests.test_mockup_prompt_preview import build_restored_generation_result
st.set_page_config(layout='wide')
app.inject_styles()
app.init_session_state()
st.session_state['sports_cave_authenticated']=True
st.session_state['selected_page']='Mockups'
st.html('<style>.fixture-nav{position:fixed;top:0;left:0;width:100%;height:64px;background:#111;color:white;z-index:10000;padding:18px 24px;box-sizing:border-box}header[data-testid="stHeader"]{display:none}</style><div class="fixture-nav">Sports Cave OS · Mockups local fixture</div>')
with st.sidebar:
    st.write('Sports Cave OS')
    st.write('Mockups')
@st.cache_resource
def sample():
    root=Path(tempfile.mkdtemp(prefix='mockups-ui-'))
    with patch.object(app.prompt_store,'get_prompt',side_effect=lambda key,default='',**kw:default):
        result=build_restored_generation_result(root)
    result['assets']=[]
    for key,label in [('black','Black Framed'),('oak','Oak Framed'),('white','White Framed'),('unframed','Unframed'),('size-guide','Size Guide')]:
        file=root/(key+'.png')
        im=Image.new('RGB',(1000,1000),'#f5f2ea');d=ImageDraw.Draw(im)
        d.rectangle((90,180,910,820),fill={'oak':'#a17a50','white':'white'}.get(key,'#151515'))
        d.rectangle((120,210,880,790),fill='#28465c');d.text((380,470),'SPORTS CAVE TEST',fill='#d4a54c');im.save(file)
        result['assets'].append(image_factory.build_asset_record(key=key,label=label,webp_path=str(file),jpg_path=str(file),asset_group='generated',zip_group=image_factory.ASSET_CATEGORY_CORE,preview_path=str(file)))
    return result
if st.session_state.last_generation_result is None:st.session_state.last_generation_result=sample()
with patch.object(app.prompt_store,'get_prompt',side_effect=lambda key,default='',**kw:default),patch.object(app,'record_activity_log'),patch.object(app,'_save_mockups_to_dropbox',side_effect=RuntimeError('Cloud writes disabled in fixture')):
    app.render_mockups_page()
