"""History presentation and state isolation; no provider or production I/O."""
from copy import deepcopy
import unittest
from unittest.mock import Mock,patch
from streamlit.testing.v1 import AppTest
from crm_composer_style import history_cell,history_date
from crm_campaign_store import CampaignStore
from crm_campaign_markets import audience
from tests.test_crm_simple_editor import document


SENT_SCRIPT='''
import streamlit as st
from unittest.mock import Mock,patch
from crm_campaign_analytics_ui import sent_table
store=Mock();store.state.return_value={}
with patch('crm_campaign_analytics_ui.sent_page',return_value=st.session_state['rows']), patch('crm_campaign_analytics_ui.details',side_effect=AssertionError('No per-row details')):
 sent_table(store,{})
'''

def sent_row():
    return {'id':'fixture','name':'Collector launch','market':'AU','sent_at':'2026-09-30T02:00:00Z',
      'updated_at':None,'recipients':1036,'delivered':1027,'delivery_rate':99.1,'opens':479,'open_rate':46.2,
      'clicks':81,'click_rate':7.8,'orders':14,'revenue':{'AUD':'2840'},'revenue_per_recipient':{'AUD':'2.74'},
      'bounces':4,'complaints':0,'archived_at':None}


class HistoryPresentationTests(unittest.TestCase):
    def test_cells_escape_content_and_preserve_full_name(self):
        html=history_cell('<script>unsafe</script>','A & B')
        self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html);self.assertIn('A &amp; B',html)
        self.assertIn('title=',html);self.assertEqual(history_date(None),'—')

    def test_sent_metrics_inline_with_compact_action_menu(self):
        at=AppTest.from_string(SENT_SCRIPT);at.session_state['rows']=[sent_row()];at.run()
        self.assertFalse(at.exception);self.assertFalse(at.metric);self.assertFalse(at.dataframe)
        rendered='\n'.join(e.proto.body for e in at.get('html'))
        for value in ('Collector launch','AUSTRALIA','1,036','1,027','99.1%','479','46.2%','81','7.8%',
                      '14','A$2,840.00','A$2.74','4 / 0','Bounces / Complaints'):
            self.assertIn(value,rendered)
        self.assertEqual([b.label for b in at.button],['View analytics','Duplicate','Archive'])
        self.assertFalse(any(b.label in ('Edit','Delete draft') for b in at.button))

    def test_zero_rates_and_empty_sent_are_readable(self):
        row=sent_row()
        for key in ('recipients','delivered','opens','clicks','orders','bounces','complaints'):row[key]=0
        for key in ('delivery_rate','open_rate','click_rate'):row[key]=None
        row['revenue']={};row['revenue_per_recipient']={}
        at=AppTest.from_string(SENT_SCRIPT);at.session_state['rows']=[row];at.run()
        self.assertFalse(at.exception)
        rendered='\n'.join(e.proto.body for e in at.get('html'))
        self.assertIn('<small>—</small>',rendered);self.assertNotIn('None%',rendered)
        at.session_state['rows']=[];at.run();self.assertFalse(at.exception)
        self.assertIn('No sent campaigns yet.',at.get('html')[0].proto.body)
        self.assertFalse(at.metric);self.assertFalse(at.dataframe)

    def test_history_counts_are_one_aggregate_without_document_reads(self):
        store=CampaignStore(Mock())
        with patch.object(store,'q',return_value={'active':2,'sent':14}) as query:
            self.assertEqual(store.history_counts(),{'active':2,'sent':14})
        query.assert_called_once()
        sql=query.call_args.args[0]
        self.assertIn('archived_at IS NULL',sql);self.assertIn('FILTER',sql)
        self.assertNotIn('document',sql)

    def test_count_label_updates_do_not_change_selected_history(self):
        script='''
import streamlit as st
from unittest.mock import Mock,patch
from crm_campaign_page import recent_campaigns
store=Mock();store.history_counts.return_value=st.session_state['counts']
with patch('crm_campaign_page.working_campaigns',side_effect=lambda *a:st.caption('Draft rows')), patch('crm_campaign_analytics_ui._sent_table',side_effect=lambda *a:st.caption('Sent rows')), patch('crm_campaign_page._selected_campaign',side_effect=AssertionError('History does not repaint editor')):
 recent_campaigns(store,'test',{})
'''
        at=AppTest.from_string(script);at.session_state['counts']={'active':2,'sent':14};at.run()
        self.assertFalse(at.exception)
        at.radio(key='campaign_history_view').set_value('Sent').run()
        at.session_state['counts']={'active':3,'sent':15};at.run()
        self.assertFalse(at.exception);self.assertEqual(at.radio(key='campaign_history_view').value,'Sent')
        self.assertEqual(at.radio(key='campaign_history_view').options,['Active  3','Sent  15'])
        self.assertEqual([c.value for c in at.caption],['Sent rows'])

    def test_automatic_count_refresh_preserves_every_draft_field(self):
        script='''
import streamlit as st
from unittest.mock import Mock,patch
from crm_campaign_controls import market_control
with patch('crm_segment_counts.COUNTS.display',return_value={'counts':st.session_state['counts'],'error':False}), patch('crm_campaign_markets.calculate',side_effect=AssertionError('No full audience scan')):
 market_control(Mock(),Mock(),st.session_state['doc'],'fixture_')
'''
        doc=document();doc.update(market_audience=True,audience=audience('AU'),
            send_timing={'mode':'schedule','date':'2026-10-20','time':'07:30'})
        before=deepcopy(doc)
        at=AppTest.from_string(script);at.session_state['doc']=doc;at.session_state['counts']={'AU':1085,'Global':2100}
        at.run();self.assertFalse(at.exception)
        self.assertIn('AUSTRALIA · 1,085',at.selectbox[0].options)
        at.session_state['counts']={'AU':1087,'Global':2102};at.run()
        self.assertFalse(at.exception);self.assertEqual(at.selectbox[0].value,'AU')
        self.assertIn('AUSTRALIA · 1,087',at.selectbox[0].options)
        self.assertEqual(at.session_state['doc'],before)
        self.assertFalse(any(b.label=='Refresh audiences' for b in at.button))

    def test_open_analytics_pauses_the_history_timer(self):
        script='''
import streamlit as st
from unittest.mock import Mock,patch
from crm_campaign_page import recent_campaigns
st.session_state['sent_analytics_id']='fixture'
with patch('crm_campaign_page._live_campaign_history',side_effect=AssertionError('No timer while dialog owns widgets')), patch('crm_campaign_page._campaign_history',side_effect=lambda *a:st.caption('Analytics history')):
 recent_campaigns(Mock(),'fixture',{})
'''
        at=AppTest.from_string(script).run();self.assertFalse(at.exception)
        self.assertEqual(at.caption[0].value,'Analytics history')
        at=AppTest.from_string(script.replace("['sent_analytics_id']","['campaign_delete_dialog_id']")).run()
        self.assertFalse(at.exception);self.assertEqual(at.caption[0].value,'Analytics history')


if __name__=='__main__':unittest.main()
