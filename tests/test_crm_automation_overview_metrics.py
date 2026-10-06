import inspect
import unittest
import os
import uuid
from crm_logic import now,recipient_hash
from crm_automation_home_data import rows
from tests.test_crm_automation_analytics import AnalyticsTests
from tests.test_crm import ADMIN
from crm_automation_home import metric_texts,STYLE_AUTO,table,table_metrics_region


class OverviewMetrics(unittest.TestCase):
    def row(self,**values):
        return dict(entered=30,sent=24,delivered=16,opened=2,clicked=1,orders=3,bounced=1,**values)

    def test_opens_keep_delivered_denominator_and_bounces_use_sent(self):
        self.assertEqual(metric_texts(self.row()),['30','24','66.7%','2 (12.5%)','6.2%','3','4.2%'])

    def test_zero_opens_and_bounces_after_real_sends(self):
        row=self.row();row.update(opened=0,bounced=0)
        self.assertEqual(metric_texts(row)[3],'0 (0.0%)')
        self.assertEqual(metric_texts(row)[6],'0.0%')

    def test_no_sends_and_unresolved_counts(self):
        row=self.row();row.update(sent=0,delivered=0,opened=0,clicked=0,bounced=0)
        self.assertEqual([metric_texts(row)[i] for i in (2,3,4,6)],['—']*4)
        self.assertEqual(metric_texts({}),['—']*7)
        row.update(sent=1,delivered=0)
        self.assertEqual(metric_texts(row)[3],'0 (—)') # no fabricated open denominator
        row['bounced']=None
        self.assertEqual(metric_texts(row)[6],'—')

    def test_first_paint_and_incremental_updates_share_formatter(self):
        for fn in (table,table_metrics_region):self.assertIn('metric_texts(row)',inspect.getsource(fn))
        source=inspect.getsource(table)
        self.assertIn("'Opens'",source);self.assertIn("'Bounce rate'",source)
        self.assertNotIn("'Revenue'",source);self.assertNotIn("'Open %'",source)
        self.assertNotIn("money(row",inspect.getsource(table_metrics_region))
        self.assertIn('.sc-auto-head,.sc-auto-row{display:grid;grid-template-columns:',STYLE_AUTO)
        self.assertIn('.sc-auto-head>div:nth-child(n+3),.sc-auto-row>div:nth-child(n+3){text-align:center}',STYLE_AUTO)
        self.assertNotIn('.sc-auto-head::after',STYLE_AUTO)


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable loopback SQL required')
class PersistedMetrics(unittest.TestCase):
    setUp=AnalyticsTests.setUp
    prepared=AnalyticsTests.prepared
    published=AnalyticsTests.published
    event=AnalyticsTests.event
    add=AnalyticsTests.add

    def test_persisted_bounces_are_per_accepted_message_and_no_send_is_empty(self):
        for label,total in [('counted',24),('zero',1)]:
            a,c=self.prepared();j=self.add(a,c)
            self.store.q('UPDATE crm_automations SET name=%s WHERE id=%s',('Overview metrics '+label+' fixture',a['id']))
            for index in range(total+1):
                send=self.store.enqueue('metric-fixture:'+str(uuid.uuid4()),self.customer['id'],recipient_hash(self.customer['email']),
                    {'id':a['steps'][0]['template_id'],'version':a['steps'][0]['template_version']},enrollment_id=j['id'],step_index=index)
                if index<total:self.store.q("UPDATE crm_marketing_sends SET status='ACCEPTED',first_submitted_at=%s WHERE id=%s",(now(),send['id']))
                events=['email.delivered'] if index<min(total,16) else []
                if label=='counted' and index<2:events+=['email.opened']*3
                if label=='counted' and index in (23,24):events+=['email.bounced']*2
                for kind in events:self.store.q('INSERT INTO crm_delivery_events(event_id,provider_id,event_type,occurred_at,send_id) VALUES(%s,%s,%s,%s,%s)',
                    (str(uuid.uuid4()),'synthetic-provider',kind,now(),send['id']))
            value=rows(self.store,search='Overview metrics '+label+' fixture')[0]
            self.assertEqual(value['sent'],total)
            self.assertEqual(metric_texts(value)[3],'2 (12.5%)' if label=='counted' else '0 (0.0%)')
            self.assertEqual(metric_texts(value)[6],'4.2%' if label=='counted' else '0.0%')
        draft=self.store.create(ADMIN,'welcome','Overview metrics draft fixture');self.created.append(str(draft['id']))
        value=rows(self.store,search='Overview metrics draft fixture')[0]
        self.assertEqual([metric_texts(value)[i] for i in (2,3,4,6)],['—']*4)
        self.provider.send.assert_not_called()


if __name__=='__main__':unittest.main()
