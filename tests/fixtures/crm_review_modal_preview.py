"""Real Campaign page over disposable SQL; delayed review, external HTTP forbidden."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import runpy
import time
import os
import logging
import subprocess
from unittest.mock import patch
import streamlit as st
from crm_campaign_send import review
logging.basicConfig(level=logging.INFO)

@st.cache_resource
def delay_review():
    def delayed(*args,**kwargs):
        time.sleep(3)
        return review(*args,**kwargs)
    if os.getenv('REVIEW_FIXTURE_BASELINE')=='1':
        import crm_campaign_page,crm_campaign_send_ui
        for module in (crm_campaign_page,crm_campaign_send_ui):
            source=subprocess.check_output(['git','show','HEAD:'+module.__name__+'.py']).decode('utf-8')
            exec(compile(source,'<baseline>','exec'),module.__dict__)
        guard=patch('crm_campaign_send_ui.review',side_effect=delayed)
    else:guard=patch('crm_campaign_review.review',side_effect=delayed)
    guard.start()
    return guard
delay_review()
st.session_state['review_fixture_page_runs']=st.session_state.get('review_fixture_page_runs',0)+1
st.html('<style>[data-testid="stHeader"]{display:none}</style><div style="height:950px">Offline scroll fixture · page render '+str(st.session_state['review_fixture_page_runs'])+'</div>')
st.html('''<div id="review-metrics" data-results="[]"></div><script>
if(!window.scReviewMetrics){
 window.scReviewMetrics={runs:[],active:null};
 const m=window.scReviewMetrics;
 const save=()=>document.getElementById('review-metrics')?.setAttribute('data-results',JSON.stringify(m.runs));
 const positions=()=>[...document.querySelectorAll('*')].filter(e=>e.scrollTop>0).map(e=>[e.getAttribute('data-testid')||e.tagName,e.scrollTop]);
 document.addEventListener('click',e=>{const b=e.target.closest('button');if(b?.textContent.trim()==='Send now'&&!b.closest('[role="dialog"]')){
  m.active={started:performance.now(),before:positions(),skeleton:false};m.runs.push(m.active);save();
 }},true);
 new MutationObserver(()=>{const a=m.active;if(!a)return;const d=document.querySelector('[role="dialog"]');
  if(d&&d.getClientRects().length&&!a.modal_ms){a.modal_ms=performance.now()-a.started;a.open=positions();}
  if(d?.textContent.includes('Preheader:')&&!a.summary_ms)a.summary_ms=performance.now()-a.started;
  if((d?.textContent.includes('Final audience ready')||/recipients · [0-9]+ excluded/.test(d?.textContent||''))&&!a.ready_ms)a.ready_ms=performance.now()-a.started;
  if(a.modal_ms&&(!d||!d.getClientRects().length)){a.closed=positions();m.active=null;}
  if(document.querySelector('.sc-email-loading'))a.skeleton=true;
  save();
 }).observe(document.body,{childList:true,subtree:true});
}
</script>''',unsafe_allow_javascript=True)
runpy.run_path(str(Path(__file__).with_name('crm_production_v2_preview.py')),run_name='__main__')
