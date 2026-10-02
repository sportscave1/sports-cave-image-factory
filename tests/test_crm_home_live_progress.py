"""Offline durable row progress, cache isolation, navigation and watchdog tests."""
from concurrent.futures import Future
from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock,patch
import unittest
from crm_campaign_home_progress import live_rows,merge_progress,accepted_home
from crm_campaign_home_cache import job
from crm_campaign_progress import summarize,read_progress
from crm_campaign_home import row_html
from crm_logic import now
from tests.test_crm_send_progress import ID,row
from tests.test_crm_campaign_home import record


class HomeLiveTests(unittest.TestCase):
    def test_progress_0_100_500_1095_then_sent(self):
        item=record();item.update(status='SENDING',delivery_status='SENDING',recipients=1095)
        original=deepcopy(item)
        for count,status in ((0,'SENDING'),(100,'SENDING'),(500,'SENDING'),(1095,'SENDING'),(1095,'SENT')):
            progress=summarize({**row(status,ACCEPTED=count,PENDING=1095-count),'worker_started_at':now()})
            merged=merge_progress([item],{ID:progress})[0]
            self.assertEqual(merged['progress']['processed'],count)
            html=row_html(merged)
            if status=='SENDING':self.assertIn(format(count,',')+' / 1,095',html)
            else:self.assertNotIn('role="progressbar"',html);self.assertIn('Sent',html)
            self.assertEqual(item,original)

    def immediate(self,state,store,key,load,**kwargs):
        self.loads.append((key,kwargs))
        f=Future();f.set_result(load())
        state.setdefault('campaign_home_cache',{})[(store.connect,key)]=(0,f)
        return f

    def test_active_read_only_visible_ids_not_history_or_metrics(self):
        state={};store=Mock();store.connect=None
        active=record();active.update(status='SENDING',delivery_status='SENDING')
        hidden={**active,'id':'00000000-0000-0000-0000-000000000002','in_page':False}
        sent={**active,'id':'00000000-0000-0000-0000-000000000003','status':'SENT','delivery_status':'SENT'}
        store.q.return_value=[row(PENDING=4)];self.loads=[]
        with patch('crm_campaign_home_progress.job',side_effect=self.immediate):
            result=live_rows(state,store,[active,hidden,sent])
        self.assertEqual(store.q.call_args.args[1],([ID],))
        self.assertEqual(self.loads[0][1],{'ttl':2.5})
        sql=store.q.call_args.args[0]
        for forbidden in ('crm_delivery_events','crm_email_orders','document','recipient_hash','email_for_provider'):
            self.assertNotIn(forbidden,sql)
        self.assertTrue(state['campaign_home_dispatch_active'])
        self.assertEqual(result[0]['progress']['total'],4)

    def test_complete_stops_fast_polling_and_keeps_last_good_analytics(self):
        store=Mock();store.connect=None;store.q.return_value=[row('SENT',ACCEPTED=4)]
        item={**record(),'status':'SENDING','delivery_status':'SENDING','delivered':2,'clicks':1}
        state={'campaign_home_resolved':{(None,('delivery',)):{'sent_emails':4}},'campaign_home_cache':{}}
        self.loads=[]
        with patch('crm_campaign_home_progress.job',side_effect=self.immediate):
            result=live_rows(state,store,[item])
            again=live_rows(state,store,[item]) # stale list must not restart polling
        self.assertFalse(state['campaign_home_dispatch_active'])
        self.assertEqual(len(self.loads),1)
        self.assertEqual((result[0]['status'],again[0]['delivered'],again[0]['clicks']),('SENT',2,1))
        self.assertEqual(state['campaign_home_resolved'][(None,('delivery',))],{'sent_emails':4})
        refreshed=merge_progress([{**item,'delivered':4,'clicks':3}],state['campaign_home_progress'])[0]
        self.assertEqual((refreshed['delivered'],refreshed['clicks']),(4,3))

    def test_status_outage_keeps_progress_and_analytics(self):
        store=Mock();store.connect=None
        item={**record(),'status':'SENDING','delivery_status':'SENDING','delivered':1}
        good=summarize(row(PENDING=2,ACCEPTED=2))
        state={'campaign_home_progress':{ID:good}}
        f=Future();f.set_exception(RuntimeError('private payload'))
        def failed(state,store,key,*args,**kwargs):
            state.setdefault('campaign_home_cache',{})[(store.connect,key)]=(0,f);return f
        with patch('crm_campaign_home_progress.job',side_effect=failed):
            result=live_rows(state,store,[item])
        self.assertEqual(result[0]['progress']['processed'],2)
        self.assertEqual(result[0]['delivered'],1)
        self.assertEqual(state['campaign_home_activity']['progress'],'ERROR')

    def test_late_status_cannot_regress_newer_progress(self):
        store=Mock();store.connect=None;self.loads=[]
        old={**row(PENDING=4),'last_progress_at':now()-timedelta(minutes=1)}
        new=summarize({**row(PENDING=1,ACCEPTED=3),'last_progress_at':now()})
        store.q.return_value=[old];state={'campaign_home_progress':{ID:new}}
        item={**record(),'status':'SENDING','delivery_status':'SENDING'}
        with patch('crm_campaign_home_progress.job',side_effect=self.immediate):result=live_rows(state,store,[item])
        self.assertEqual(result[0]['progress']['processed'],3)

    def test_stalled_report_without_send_mutation_and_scheduled_future_not_stalled(self):
        from crm_campaign_progress import polling_seconds
        stale={**row(PENDING=4),'updated_at':now()-timedelta(minutes=11)}
        self.assertTrue(summarize(stale)['stalled'])
        self.assertEqual(polling_seconds(summarize(stale)),30)
        self.assertEqual(polling_seconds(summarize(row(UNCERTAIN=4))),30)
        self.assertFalse(summarize({**stale,'next_due_at':now()+timedelta(days=1)})['stalled'])
        self.assertFalse(summarize({**stale,'status':'SCHEDULED'})['stalled'])
        html=row_html({**record(),'status':'SENDING','progress':summarize(stale)})
        self.assertIn('Stalled',html)

    def test_real_terminal_failure_and_partial_failure_labels(self):
        for status,counts,label in (('FAILED',{'FAILED':4},'Failed'),('SENT',{'ACCEPTED':3,'FAILED':1},'Sent with issues'),('SENDING',{'UNCERTAIN':4},'Needs attention')):
            html=row_html({**record(),'status':status,'progress':summarize(row(status,**counts))})
            self.assertIn(label,html)

    def test_accepted_preserves_editor_and_known_identity_only(self):
        editor={'id':ID,'name':'Collector','document':{'market':'AU','content':{'subject':'Real subject'}}}
        state={'campaign_editor':deepcopy(editor),'campaign_home_tab':'Drafts','campaign_send_dialog_id':ID}
        accepted_home(state,{'id':ID,'status':'SENDING','recipients':1095},editor)
        self.assertEqual(state['campaign_editor'],editor)
        self.assertEqual(state['campaign_home_accepted']['subject'],'Real subject')
        self.assertNotIn('delivered',state['campaign_home_accepted'])
        self.assertNotIn('campaign_send_dialog_id',state)
        self.assertNotIn('campaign_home_tab',state)
        accepted_home(state,{'id':ID,'status':'SCHEDULED'},editor)
        self.assertEqual(state['campaign_home_notice'],'Campaign scheduled')

    def test_new_session_restores_from_durable_rows(self):
        store=Mock();store.connect=None;store.q.return_value=[row(PENDING=1,ACCEPTED=3)]
        self.loads=[]
        with patch('crm_campaign_home_progress.job',side_effect=self.immediate):
            result=live_rows({},store,[{**record(),'status':'SENDING','delivery_status':'SENDING'}])
        self.assertEqual(result[0]['progress']['processed'],3)

    def test_scheduled_to_sending_to_sent_uses_same_durable_path(self):
        store=Mock();store.connect=None;state={};self.loads=[]
        item={**record(),'status':'SCHEDULED','delivery_status':'SCHEDULED'}
        for status in ('SCHEDULED','SENDING','SENT'):
            store.q.return_value=[{**row(status,PENDING=4 if status!='SENT' else 0,ACCEPTED=4 if status=='SENT' else 0),
                'scheduled_at':now()+timedelta(days=1) if status=='SCHEDULED' else None}]
            with patch('crm_campaign_home_progress.job',side_effect=self.immediate):
                result=live_rows(state,store,[item])
            self.assertEqual(result[0]['status'],status)
            self.assertEqual(state['campaign_home_dispatch_active'],status=='SENDING')
        self.assertEqual(self.loads[0][1],{'ttl':30})

    def test_polling_cache_deduplicates_and_does_not_expire_analytics(self):
        state={};store=Mock();store.connect=None;loader=Mock(return_value=[])
        with patch('crm_campaign_home_cache.monotonic',return_value=0):
            first=job(state,store,('progress',(ID,)),loader,ttl=2.5);first.result(timeout=2)
            self.assertIs(job(state,store,('progress',(ID,)),loader,ttl=2.5),first)
            table=job(state,store,('table',),loader);table.result(timeout=2)
            job(state,store,('table',),loader)
        with patch('crm_campaign_home_cache.monotonic',return_value=3):
            second=job(state,store,('progress',(ID,)),loader,ttl=2.5);second.result(timeout=2)
            self.assertIsNot(first,second)
            self.assertIs(job(state,store,('table',),loader),table)
        self.assertEqual(loader.call_count,3)

    def test_progress_logs_only_ids_counts_timestamps(self):
        store=Mock();store.connect=None;store.q.return_value=[row(PENDING=4)];self.loads=[]
        with patch('crm_campaign_home_progress.job',side_effect=self.immediate),self.assertLogs('crm_campaign_home_progress',level='INFO') as logs:
            live_rows({},store,[{**record(),'status':'SENDING','delivery_status':'SENDING'}])
        message=' '.join(logs.output)
        for forbidden in ('Real fixture campaign','subject','@','token','<html'):
            self.assertNotIn(forbidden,message)
        self.assertIn('status_poll_count=1',message);self.assertIn('processed=0',message)


if __name__=='__main__':unittest.main()
