"""Shared recipient state and immutable per-flow receipt contracts."""
from copy import deepcopy
from unittest.mock import Mock,patch
import os,unittest
from crm_flow_recipients import selection,table_event,read_page,restore
from crm_flow_recipient_adapters import LIFECYCLE,project
from crm_lifecycle_definition import expanded_flow
from crm_automation_definition import new_flow
from crm_logic import now


class SharedStateTests(unittest.TestCase):
    def test_panel_restores_disclosure_without_overwriting_retained_filters(self):
        from crm_flow_recipients import panel
        state={'flow-panel-open':True,'flow-search':'','flow-search-retained':'new search'}
        with patch('crm_flow_recipients.st') as ui:
            ui.session_state=state
            ui.expander.return_value.__enter__.return_value.open=True
            body=Mock()
            panel.__wrapped__('Recipients','flow',body)
            self.assertTrue(state['flow-panel']);self.assertEqual(state['flow-search'],'new search')
            state['flow-panel']=False
            ui.expander.call_args.kwargs['on_change']()
            self.assertFalse(state['flow-panel-open'])
            body.assert_called_once()

    def test_detail_escape_does_not_clear_selection_or_accept_stale_context(self):
        state={'flow-selected':['x'],'flow-detail':'x','flow-visible':['x'],'flow-table-context':'current'}
        state['flow-table']=dict(context='old',sequence=1,close_detail=True,selected=['x'])
        with patch('crm_flow_recipients.st.session_state',state):table_event('flow')
        self.assertEqual(state['flow-detail'],'x')
        state['flow-table'].update(context='current',sequence=2)
        with patch('crm_flow_recipients.st.session_state',state):table_event('flow')
        self.assertNotIn('flow-detail',state);self.assertEqual(state['flow-selected'],['x'])

    def test_pagination_uses_callback_without_extra_rerun(self):
        from crm_flow_recipients import pagination
        previous=Mock();next_page=Mock()
        with patch('crm_flow_recipients.st') as ui:
            pagination('fixture',0,50,True,previous,next_page)
            self.assertEqual(ui.button.call_args_list[0].kwargs['on_click'],previous)
            self.assertTrue(ui.button.call_args_list[0].kwargs['disabled'])
            self.assertEqual(ui.button.call_args_list[1].kwargs['on_click'],next_page)
            ui.rerun.assert_not_called();previous.assert_not_called();next_page.assert_not_called()

    def test_checkout_honours_explicit_shared_wait_budget(self):
        from crm_automation_analytics_ui import read
        future=Mock();future.done.return_value=False
        with patch('crm_automation_analytics_ui.job',return_value=future),patch('crm_automation_analytics_ui.state',return_value={}),patch('crm_automation_analytics_ui.resolve',return_value=([], 'READY')):
            read(Mock(),('checkout-list','fixture'),lambda:[],wait_budget=.15)
            future.result.assert_called_once_with(timeout=.15)

    def test_checkout_read_does_not_install_a_second_settlement_timer(self):
        from crm_flow_page import _checkouts
        with patch('crm_flow_page.st') as ui,patch('crm_flow_page.checkout_panel') as panel,patch('crm_flow_page.arm') as arm:
            ui.session_state={}
            panel.side_effect=lambda *a,**k:ui.session_state.update({'automation-analytics-pending':True})
            _checkouts.__wrapped__(None,Mock(),{}, {'id':'fixture'})
            arm.assert_not_called()
            panel.side_effect=lambda *a,**k:ui.session_state.update({'checkout-enrollment-pending':True})
            _checkouts.__wrapped__(None,Mock(),{}, {'id':'fixture'})
            arm.assert_called_once_with('flow-checkouts',1)

    def test_every_flow_uses_same_save_error_and_success_boundary(self):
        from crm_flow_page import commit
        for kind in ('abandoned',*LIFECYCLE):
            with self.subTest(kind=kind),patch('crm_flow_page.st') as ui,patch('crm_flow_page.save') as save:
                ui.session_state={};row={'id':'fixture','trigger_type':kind}
                save.side_effect=ValueError('Draft changed; reload')
                commit(Mock(),{},row,{})
                ui.error.assert_called_once_with('Draft changed; reload');ui.rerun.assert_not_called()
                self.assertNotIn('flow-toolbar-dirty',ui.session_state)
                save.side_effect=None;save.return_value=True
                commit(Mock(),{},row,{})
                self.assertTrue(ui.session_state['flow-toolbar-dirty'])
                ui.rerun.assert_called_once_with(scope='fragment')

    def test_all_flows_retain_off_page_selection_and_refresh_cannot_undo_a_click(self):
        for kind in ('abandoned',*LIFECYCLE):
            with self.subTest(kind=kind):
                state={kind+'-selected':['previous']}
                selection(state,kind,{'current'},{'sequence':1,'selected':['current']})
                selection(state,kind,{'current'},{'sequence':2,'refresh':True,'selected':[]})
                self.assertEqual(state[kind+'-selected'],['current','previous'])
                selection(state,kind,{'current'},{'sequence':3,'selected':[],'clear_selection':True})
                self.assertEqual(state[kind+'-selected'],[])
                state[kind+'-selected']=['newer']
                selection(state,kind,{'current'},{'sequence':3,'selected':[],'clear_selection':True})
                self.assertEqual(state[kind+'-selected'],['newer'])

    def test_context_fence_rejects_stale_detail_retry_and_global_clear(self):
        state={'flow-selected':['safe'],'flow-visible':['x'],'flow-table-context':'page2',
            'flow-table':dict(context='page1',sequence=1,clear_selection=True,detail='x',retry='x')}
        with patch('crm_flow_recipients.st.session_state',state):table_event('flow')
        self.assertEqual(state['flow-selected'],['safe'])
        self.assertNotIn('flow-detail',state);self.assertNotIn('flow-retry',state)

    def test_restoration_reasserts_retained_value_before_widget_remount(self):
        state={'flow-search':'','flow-search-retained':'saved','flow-sort-retained':'Oldest'}
        with patch('crm_flow_recipients.st.session_state',state):restore('flow')
        self.assertEqual(state['flow-search'],'saved');self.assertEqual(state['flow-sort'],'Oldest')

    def test_shared_reads_keep_stale_rows_but_never_cross_revision_or_filters(self):
        session={};store=Mock(connect='fixture');key=('recipients','flow','revision1','search1');rows=[{'key':'one'}]
        with patch('crm_flow_recipients.st.session_state',session),patch('crm_automation_analytics_ui.read') as read,\
             patch('crm_automation_analytics_ui.state',return_value={}),patch('crm_automation_home.arm_section') as arm:
            read.return_value=(rows,'READY');self.assertEqual(read_page(store,'flow',key,lambda:None,30)[0],rows)
            read.return_value=(None,'ERROR');self.assertEqual(read_page(store,'flow',key,lambda:None,30)[0],rows)
            self.assertIsNone(read_page(store,'flow',key+('changed',),lambda:None,30)[0])
            read.return_value=(None,'NOT_STARTED');read_page(store,'flow',key,lambda:None,30);arm.assert_called()
            read.return_value=([],'READY');self.assertEqual(read_page(store,'flow',key,lambda:None,30)[0],[])
            for i in range(20):read_page(store,'flow',('recipients',i),lambda:None,30)
            self.assertEqual(len(session['flow-snapshots']),8)

    def test_every_projection_uses_published_columns_and_preserves_source(self):
        for kind,adapter in LIFECYCLE.items():
            with self.subTest(kind=kind):
                flow=new_flow(kind) if kind=='fulfilled' else expanded_flow(kind)
                row=dict(trigger_type=kind,status='ACTIVE',config={'draft':deepcopy(flow),'published_flow':flow})
                row['config']['draft']['emails'].pop()
                record=dict(key='x',customer_id='customer',name='Fixture',email='fixture@example.test',consent='SUBSCRIBED',
                    suppressed=False,flow_state='ACTIVE',enrollment_id='journey',current_step=0,steps=flow['emails'],sends=[],
                    next_due_at=now(),audience_at=now(),order_count=1,source='Fixture',last_paid_at=now(),lifetime_value=10,
                    currency='AUD',order_name='#Fixture',financial_status='PAID',fulfillment_status='UNFULFILLED',reference='#Fixture')
                original=deepcopy(record)
                columns,rows=project(adapter,row,[record],str,now())
                self.assertEqual([c['id'] for c in columns if 'id' in c],[s['step_id'] for s in flow['emails']])
                self.assertEqual(len(rows[0]['cells']),len(columns));self.assertEqual(record,original)
                if kind=='welcome':
                    self.assertEqual([c['label'] for c in columns if c.get('visible',True)],['Flow','Purchased','Email 1','Email 2','Email 3'])
                    self.assertIn('Email',[c['label'] for c in columns])
                    self.assertIn('Consent',[c['label'] for c in columns])
                    self.assertIn('Source',[c['label'] for c in columns])
                    self.assertEqual([c['label'] for c in rows[0]['cells'][:5]],
                        ['fixture@example.test','SUBSCRIBED','ACTIVE','Yes','Fixture'])
                else:self.assertTrue(all(c.get('visible',True) for c in columns))


@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class NativeSourceTests(unittest.TestCase):
    def test_fulfilled_source_is_read_only_and_scoped_to_existing_journeys(self):
        from tests.test_crm_lifecycle_expansion import DatabaseTests
        from tests.crm_db_fixture import connect
        from crm_automation_store import AutomationStore
        from crm_native_audience import listing
        from tests.test_crm import ADMIN
        from tests.test_crm_send_flow import CFG
        DatabaseTests.setUpClass();store=AutomationStore(connect)
        with patch.object(store,'render_settings',return_value=CFG):row=store.create(ADMIN,'fulfilled')
        before=store.q('SELECT count(*) AS n FROM crm_automation_enrollments',one=True)['n']
        for sort in ('Newest','Oldest','Sequence stage'):
            self.assertEqual(listing(store,row,sort=sort,search='fixture'),[])
        self.assertEqual(store.q('SELECT count(*) AS n FROM crm_automation_enrollments',one=True)['n'],before)


if __name__=='__main__':unittest.main()
