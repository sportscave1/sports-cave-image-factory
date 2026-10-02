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

    def test_history_compatibility_entry_is_home_only(self):
        from crm_campaign_page import recent_campaigns
        store=Mock()
        with patch('crm_campaign_home.home') as home:
            recent_campaigns(store,'unused',{})
        home.assert_called_once_with(store,{})

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

    def test_dialog_open_suspends_home_timer(self):
        from pathlib import Path
        source=Path('crm_campaign_home.py').read_text(encoding='utf-8')
        self.assertIn("not st.session_state.get('sent_analytics_id')",source)
        self.assertIn("not st.session_state.get('campaign_delete_dialog_id')",source)


if __name__=='__main__':unittest.main()
