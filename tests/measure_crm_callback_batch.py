"""One bounded before/after SQL run. All recipients and receipts are fabricated."""
import json
import subprocess
import time
from unittest.mock import patch
import uuid


def main():
    from tests.test_crm_batch_dispatch import DispatchTests
    from crm_campaign_dispatch import dispatch
    from crm_webhooks import receive_resend
    from crm_logic import now
    import crm_resend_event_worker as current
    import crm_workspace_store
    old_worker={'__name__':'callback_baseline_worker'}
    old_records={'__name__':'callback_baseline_records'}
    for filename,namespace in [('crm_resend_event_worker.py',old_worker),('crm_workspace_store.py',old_records)]:
        exec(compile(subprocess.check_output(['git','show','HEAD:'+filename]).decode(),'<released-baseline>','exec'),namespace)
    for baseline in (True,False):
        fixture=DispatchTests();fixture.setUp();events=[]
        try:
            identity=fixture.queue(20);dispatch(fixture.engine)
            recipients=fixture.sends(identity)
            with patch.object(current,'log'):
                for i in range(100):
                    event='evt_'+uuid.uuid4().hex;events.append(event)
                    receive_resend(fixture.store,event,{'type':['email.delivered','email.opened','email.clicked'][i%3],
                      'created_at':now().isoformat(),'data':{'email_id':recipients[i%20]['provider_email_id']}},defer=True)
            original=fixture.store.connect;counters={'transactions':0,'statements':0}
            class Counted:
                def __enter__(self):
                    counters['transactions']+=1;self.conn=original();self.conn.__enter__();return self
                def __exit__(self,*args):return self.conn.__exit__(*args)
                def execute(self,*args,**kwargs):counters['statements']+=1;return self.conn.execute(*args,**kwargs)
            fixture.store.connect=Counted
            processed=0;started=time.perf_counter()
            with patch.object(current,'log'),patch.dict(old_worker,{'log':lambda *a,**k:None}):
                if baseline:
                    with patch.object(crm_workspace_store,'WorkspaceRecords',old_records['WorkspaceRecords']):
                        while processed<100:processed+=old_worker['run_once'](fixture.store)
                else:
                    while processed<100:processed+=current.run_once(fixture.store)
            elapsed=(time.perf_counter()-started)*1000
            fixture.store.connect=original
            delivered=fixture.store.q('SELECT count(DISTINCT s.id) AS n FROM crm_marketing_sends s JOIN crm_delivery_events e ON e.send_id=s.id WHERE s.campaign_id=%s AND e.event_type=%s',(identity,'email.delivered'),True)['n']
            print(json.dumps({'baseline':baseline,'events':processed,'delivered_recipients':delivered,'elapsed_ms':round(elapsed,2),**counters}))
        finally:
            for event in events:
                fixture.store.q("DELETE FROM crm_webhook_events WHERE provider='resend' AND event_id=%s",(event,))
                fixture.store.q('DELETE FROM crm_delivery_events WHERE event_id=%s',(event,))
            fixture.tearDown();fixture.doCleanups()

if __name__=='__main__':main()
