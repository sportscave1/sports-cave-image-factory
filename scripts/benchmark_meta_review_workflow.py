"""Offline Streamlit/Python rerun timings, not browser or Meta latency."""
import copy
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if os.environ.get('META_REVIEW_MODULE_ROOT'):sys.path.insert(0,os.environ['META_REVIEW_MODULE_ROOT'])
from streamlit.testing.v1 import AppTest
import ads_meta_review_page as page
from tests.test_meta_review_live import CONFIG
from tests.test_meta_review_search import ROWS
from scripts.benchmark_meta_review_v3 import measure

def run():
    with patch.object(page.meta,'get_meta_config',return_value=CONFIG), \
         patch.object(page.live,'load_overview',side_effect=lambda *a:{'account':{'currency':'AUD'},'campaigns':copy.deepcopy(ROWS)}) as overview, \
         patch.object(page.recency,'load',return_value={'available':False}), \
         patch.object(page.meta,'_request',side_effect=AssertionError('No network')):
        def cold():
            app=AppTest.from_string('import ads_meta_review_page as p\np.render_page()',default_timeout=15).run()
            assert not app.exception
            return app
        app=cold()
        def refresh():
            reads=overview.call_count
            next(b for b in app.button if b.label=='Refresh From Meta').click().run()
            assert not app.exception
            assert overview.call_count==reads+1
        out={'new_session_mock':measure(cold,20),'warm_full_rerun':measure(app.run,20),
             'manual_refresh_mock':measure(refresh,20,prepare=app.run)}
        out['search_full_rerun']=measure(lambda:app.text_input[0].input('brock').run(),20)
        app.text_input[0].input('').run()
        out['sort_full_rerun']=measure(lambda:app.selectbox[0].select('Spend').run(),20)
        print(json.dumps(out,indent=2))
if __name__=='__main__':run()
