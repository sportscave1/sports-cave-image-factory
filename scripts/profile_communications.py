"""Opt-in LOCAL fixture profiler. Start tests/crm_postgres_server.mjs first.

Uses actual UI/controllers with fake mail/Shopify and disposable loopback SQL.
No production endpoints, credentials or sends; not imported by the application.
Run: python scripts/profile_communications.py > .venv/communications-before.json
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collections import Counter
from contextlib import ExitStack
import json
import os
import time
from unittest.mock import patch

os.environ['CRM_MARKETING_ENABLED'] = 'false'


def profile():
    from streamlit.testing.v1 import AppTest
    from tests.test_crm_ui import SCRIPT
    from tests.crm_db_fixture import connect
    from crm_store import Store
    from crm_campaign_html import EmailHTML
    from tests.test_support_email_v2 import WorkspaceTests
    from tests.test_crm_campaign_sections import sectioned
    from tests.test_crm_resend_marketing import ENV
    from crm_campaign_content import render_campaign, settings
    Store(connect).seed()
    counts=Counter(); elapsed=Counter(); results={}

    def measured(name, fn):
        def run(*args, **kwargs):
            start=time.perf_counter()
            try:return fn(*args, **kwargs)
            finally:
                counts[name]+=1;elapsed[name]+=time.perf_counter()-start
        return run

    def sample(name, call):
        counts.clear();elapsed.clear();start=time.perf_counter()
        result=call()
        if hasattr(result,'exception') and result.exception:raise RuntimeError(str(result.exception))
        results[name]={'total_ms':round((time.perf_counter()-start)*1000,2),
                       'calls':dict(counts),'operation_ms':{k:round(v*1000,2) for k,v in elapsed.items()}}
        return result

    with ExitStack() as stack:
        stack.enter_context(patch.object(Store,'q',measured('database_read',Store.q)))
        stack.enter_context(patch.object(EmailHTML,'feed',measured('sanitizer',EmailHTML.feed)))
        stack.enter_context(patch('requests.sessions.Session.request',side_effect=AssertionError('External HTTP forbidden')))
        script=SCRIPT.replace('store=Store(connect);store.seed()','store=Store(connect)')
        at=AppTest.from_string(script);at.session_state['route']='CRM Campaigns'
        sample('campaign_initial',lambda:at.run(timeout=30))
        body='<table><tr><td style="color:#111111;padding:12px">Collector artwork</td></tr></table>'*400
        next(t for t in at.text_area if t.label=='Body HTML').set_value(body)
        sample('campaign_paste_38kb',lambda:at.run(timeout=30))
        for device in ('Mobile','Desktop'):
            button=next(b for b in at.button if (b.key or '').endswith('device_'+device))
            sample('campaign_'+device.lower(),lambda b=button:b.click().run(timeout=30))
        sample('campaign_unchanged_rerun',lambda:at.run(timeout=30))
        flow=AppTest.from_string(script);flow.session_state['route']='CRM Automations'
        sample('flow_initial',lambda:flow.run(timeout=30))
        sample('flow_preview',lambda:next(b for b in flow.button if b.label=='Preview').click().run(timeout=30))
        sample('flow_unchanged_rerun',lambda:flow.run(timeout=30))
        width=next(s for s in flow.selectbox if s.label=='Width')
        sample('flow_mobile',lambda:width.set_value(390).run(timeout=30))
        doc=sectioned();doc['custom_html']=body
        sample('canonical_html_38kb',lambda:render_campaign(doc,settings(ENV)))

        inbox=WorkspaceTests();inbox.setUp()
        try:
            for method in ('discover_folders','list_headers','read_message','related_headers_many'):
                stack.enter_context(patch.object(inbox.imap,method,measured(method,getattr(inbox.imap,method))))
            import support_email_store
            stack.enter_context(patch.object(support_email_store,'load_orders',measured('enrichment',support_email_store.load_orders)))
            inbox.state.clear()
            from support_email_workspace import Workspace
            inbox.w=Workspace(inbox.state,inbox.w.user,inbox.w.config,inbox.w.smtp_config,imap=inbox.imap,smtp=inbox.smtp)
            sample('inbox_initial',lambda:(inbox.w.load(),inbox.w.model()))
            sample('inbox_cached_model',lambda:inbox.w.model())
            sample('inbox_refresh',lambda:inbox.event('refresh'))
            sample('inbox_other_message',lambda:inbox.event('open_thread',thread_key=inbox.state['threads'][1]['thread_key']))
            sample('inbox_enrichment',lambda:inbox.event('context'))
        finally:inbox.doCleanups()
    return results


if __name__=='__main__':
    print(json.dumps(profile(),indent=2))
