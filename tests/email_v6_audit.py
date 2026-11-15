"""Reproducible backend baseline; no production data, HTTP, or provider calls."""
from copy import deepcopy
import json
import os
from pathlib import Path
import statistics
import time
from unittest.mock import Mock,patch
from crm_local_preview import model
from crm_middle_sections import commit_middle,middle_sections,apply_event
from crm_recovery_discount import substitute
from tests.test_crm_campaign_sections import sectioned
from tests.test_crm_discount_editor_v2 import add
from tests.test_crm_send_flow import CFG
from tests.test_crm_abandoned_checkout import checkout
from crm_abandoned_checkout import context

def summary(values):return {'p50_ms':statistics.median(values),'p95_ms':sorted(values)[max(0,__import__('math').ceil(len(values)*.95)-1)],'samples':values}
def main():
    result={'label':os.getenv('EMAIL_V6_LABEL','baseline'),'restrictions':{},'server_model':{}}
    for kind,source in [('code','<p>{{discount_code}}</p>'),('amount','<p>{{discount_value}}</p>'),('text','<p>A personal invitation</p>'),('unfinished','<table><tr><td>')]:
        doc=sectioned();add(doc);doc['middle_sections'][-1]['html']=source;commit_middle(doc,doc['middle_sections'])
        with patch('streamlit.session_state',{}):seed=model(doc,CFG)
        result['restrictions'][kind]={'preview_errors':seed['errors'],'source_retained':doc['middle_sections'][-1]['html']==source}
    doc=sectioned();add(doc);selected=deepcopy(doc['recovery_discount']);sections=middle_sections(doc);sections[-1]['visible']=False;commit_middle(doc,sections)
    result['restrictions']['hidden_association_retained']=doc.get('recovery_discount')==selected
    data=context(checkout(items=2))
    for n in (3,30):
        doc=sectioned();commit_middle(doc,[dict(id='s'+str(i),type='html',html_number=i+1,visible=True,html='<p style="color:#abcdef">Creative copy '+str(i)+'</p>'*20) for i in range(n)])
        for mode in ('cold_context','warm_context'):
            values=[];state={'_automation_checkout_pin':{'last_good':data}};calls=[]
            def gallery(*a,**k):calls.append(1);time.sleep(.075);return []
            with patch('streamlit.session_state',state),patch('crm_lifestyle_images.gallery',side_effect=gallery),patch('crm_frame_banner_template.resolve',side_effect=lambda d,*a:deepcopy(d)),patch('requests.sessions.Session.request',side_effect=AssertionError('External request forbidden')):
                if mode=='warm_context':model(doc,CFG,Mock(email_mode='automation'))
                for sample in range(12):
                    if mode=='cold_context':state.clear();state['_automation_checkout_pin']={'last_good':data}
                    started=time.perf_counter();model(doc,CFG,Mock(email_mode='automation'));values.append((time.perf_counter()-started)*1000)
            result['server_model'][str(n)+'_'+mode]=summary(values)|{'gallery_calls':len(calls),'simulated_gallery_latency_ms':75}
    path=Path('tmp/email-v6-'+result['label']+'-backend.json');path.write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
