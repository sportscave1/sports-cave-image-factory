"""One bounded comparison; synthetic 2,242 recipients and fake provider only."""
from copy import deepcopy
import json
import subprocess
import time
from types import SimpleNamespace
import uuid
from unittest.mock import patch
from crm_campaign_store import CampaignStore
from crm_campaign_send import review
from crm_campaign_preparation import accept,tick,lookup
from crm_campaign_progress import read_progress
from crm_campaign_dispatch import dispatch
from crm_engine import Engine
from crm_resend import Config
from tests.crm_db_fixture import connect
from tests.test_crm_campaign_v2 import profile,authority
from tests.test_crm_send_flow import CFG,LIVE
from tests.test_crm_simple_editor import document
from tests.test_crm import ADMIN
from tests.test_crm_batch_dispatch import Transport


def main():
    old={}
    exec(compile(subprocess.check_output(['git','show','HEAD:crm_campaign_send.py']).decode(),'<released-send>','exec'),old)
    for baseline in (True,False):
        store=CampaignStore(connect);store.db=connect
        seed=uuid.uuid4().int%1000000000
        shop=authority([profile(seed+i) for i in range(2242)])
        from crm_campaign_markets import audience
        doc=document();doc.update(market='AU',market_audience=True,audience=audience('AU'))
        timings={};start=time.perf_counter()
        reviewed_cfg={**deepcopy(CFG),'test_unsubscribe_url':'https://preview.example.test/crm/unsubscribe/test'}
        with patch('requests.sessions.Session.request',side_effect=AssertionError('External requests forbidden')),patch.object(store,'render_settings',return_value=reviewed_cfg):
            editor=store.save(ADMIN,'Offline timing '+uuid.uuid4().hex,doc,env=LIVE)
            t=time.perf_counter();result=(old['review'] if baseline else review)(shop,store,editor,LIVE)
            timings['review_ms']=round((time.perf_counter()-t)*1000,2)
            t=time.perf_counter();accept(store,ADMIN,editor,str(uuid.uuid4()),snapshot_id=result['snapshot_id'],confirmed=True,env=LIVE)
            timings['durable_acceptance_ms']=round((time.perf_counter()-t)*1000,2)
            t=time.perf_counter()
            with patch.object(store,'render_settings',return_value={**reviewed_cfg,'test_unsubscribe_url':''}):
                if baseline:
                    with patch('crm_campaign_send.queue_campaign',old['queue_campaign']):tick(store,shop,env=LIVE)
                else:tick(store,shop,env=LIVE)
            timings['worker_claim_prepare_ms']=round((time.perf_counter()-t)*1000,2)
            transport=Transport();engine=Engine(store,shop,SimpleNamespace(batch_transport=transport),Config(LIVE))
            if not baseline:
                store.q("UPDATE crm_marketing_sends SET due_at=now()-interval '1 second' WHERE campaign_id=%s",(editor['id'],))
                t=time.perf_counter()
                for _ in range(3):
                    if not dispatch(engine):break
                timings['fake_provider_dispatch_ms']=round((time.perf_counter()-t)*1000,2)
            t=time.perf_counter();progress=read_progress(store,[editor['id']])[str(editor['id'])]
            timings['status_read_ms']=round((time.perf_counter()-t)*1000,2)
            timings['total_ms']=round((time.perf_counter()-start)*1000,2)
            print(json.dumps({'baseline':baseline,'timings':timings,'status':lookup(store,ADMIN,editor['id'])['status'],
                'recipient_jobs':store.q('SELECT count(*) AS n FROM crm_marketing_sends WHERE campaign_id=%s',(editor['id'],),True)['n'],
                'provider_batches':len(transport.calls),'fake_accepted':progress['submitted']}))
            store.q("UPDATE crm_campaigns SET status='PAUSED' WHERE id=%s AND status='SENDING'",(editor['id'],))

if __name__=='__main__':main()
