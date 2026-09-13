import copy
from datetime import datetime,timedelta,timezone
from contextlib import contextmanager
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlparse
from streamlit.testing.v1 import AppTest
import meta_review_recency as sale
import meta_review_live as live
import meta_review_tables as tables
import meta_review_handoff as handoff
import meta_review_store as store
import ads_meta_review_page as page
import meta_ads_client as meta
from tests.test_meta_review import history,ad
from tests.test_meta_review_live import CONFIG

NOW=datetime(2026,9,13,12,tzinfo=timezone.utc)


def evidence(hours=None):
    latest={} if hours is None else {'1':{'start':(NOW-timedelta(hours=hours+1)).isoformat(),'end':(NOW-timedelta(hours=hours)).isoformat()}}
    return {'available':True,'latest':latest,'checked_at':NOW.isoformat(),'window_start':(NOW-timedelta(hours=72)).isoformat()}


class LastSaleTests(unittest.TestCase):
    def row(self,status='ACTIVE',purchases=1,age=None):
        return {'campaign_id':'1','status':status,'metrics':{'purchases':purchases},'benchmark':{'recommendation':'TOP WINNER'},
                'start_time':(NOW-timedelta(hours=age)).isoformat() if age is not None else None}

    def test_sale_bands_and_active_override(self):
        for hours,band,action in [(6,'GREEN','TOP WINNER'),(31,'AMBER','CONSIDER'),(50,'RED','STOP CAMPAIGN')]:
            r=sale.signal(self.row(),evidence(hours),NOW)
            self.assertEqual((r['band'],r['action']),(band,action))
        row=self.row(); row['benchmark']['recommendation']='STOP / REPLACE'
        self.assertEqual(sale.signal(row,evidence(31),NOW)['action'],'STOP / REPLACE')
        self.assertEqual(sale.signal(row,evidence(6),NOW)['action'],'STOP / REPLACE')

    def test_no_sale_age_rules(self):
        for age,expected in [(14,'LEARNING'),(31,'CONSIDER'),(51,'STOP CAMPAIGN')]:
            r=sale.signal(self.row(purchases=0,age=age),evidence(),NOW)
            self.assertEqual(r['action'],expected); self.assertIn('No sale yet',r['text'])

    def test_paused_archived_never_stop(self):
        for status in ('PAUSED','ARCHIVED'):
            for hours in (6,31,50,None):
                self.assertEqual(sale.signal(self.row(status),evidence(hours),NOW)['action'],status)

    def test_unknown_failed_stale_or_missing_age_never_fake_timestamp(self):
        row=self.row(purchases=0)
        for data in (None,{'available':False},evidence()):
            self.assertEqual(sale.signal(row,data,NOW)['text'],'Unavailable')
        self.assertEqual(sale.signal(self.row(),evidence(6),NOW+timedelta(minutes=4))['text'],'Unavailable')
        self.assertEqual(sale.signal(self.row(),evidence(23.5),NOW)['band'],'NEUTRAL')

    def test_hourly_request_canonical_purchase_only_and_timezone(self):
        rows=[{'campaign_id':'1','date_start':'2026-09-13','date_stop':'2026-09-13',sale.HOURLY:'16:00:00 - 16:59:59',
               'actions':[{'action_type':'offsite_conversion.fb_pixel_purchase','value':'1'},{'action_type':'purchase','value':'99'},{'action_type':'omni_purchase','value':'99'}]},
              {'campaign_id':'1','date_start':'2026-09-13','date_stop':'2026-09-13',sale.HOURLY:'20:00:00 - 20:59:59',
               'actions':[{'action_type':'omni_purchase','value':'99'}]}]
        with patch.object(live.Reader,'pages',return_value=rows) as read:
            data=sale.load(CONFIG,'act_123','campaign',now=NOW)
        params=read.call_args.args[1]
        self.assertEqual(params['fields'],'campaign_id,date_start,date_stop,actions')
        self.assertEqual(params['breakdowns'],sale.HOURLY)
        self.assertEqual(params['action_report_time'],'conversion')
        self.assertEqual(params['time_increment'],1)
        self.assertEqual(data['latest']['1']['start'],'2026-09-13T06:00:00+00:00')

    def test_malformed_and_unsupported_hourly_are_unavailable(self):
        with patch.object(live.Reader,'pages',side_effect=meta.MetaAdsApiError('Unsupported breakdown',error_code=100)):
            self.assertFalse(sale.load(CONFIG,'1','ad',now=NOW)['available'])
        with patch.object(live.Reader,'pages',return_value=[{'ad_id':'1','actions':[{'action_type':'offsite_conversion.fb_pixel_purchase','value':'1'}]}]):
            self.assertFalse(sale.load(CONFIG,'1','ad',now=NOW)['available'])


class PresentationTests(unittest.TestCase):
    def test_minimal_columns_and_advanced_nonduplication(self):
        row={'campaign_id':'1','metrics':{'spend':25,'purchases':2,'cpc':.1}}
        self.assertEqual(list(tables.va_campaign_rows([row])[0]),['Campaign','Status','Spend','Sales','ROAS','CPA','CTR','CPC','ATC','Checkout','Last Sale','Action'])
        self.assertNotIn('CPC',{r['Metric'] for r in tables.advanced_rows(row['metrics'],campaign=True)})
        creative=tables.va_ad_rows([ad()])[0]
        self.assertEqual(list(creative),['Creative','Ad','Sales','ROAS','CPA','CTR','ATC','Checkout','Last Sale','Action'])
        advanced={r['Metric'] for r in tables.advanced_rows(row['metrics'])}
        self.assertIn('CPC (all clicks)',advanced); self.assertNotIn('ROAS',advanced); self.assertNotIn('Spend',advanced)
        self.assertNotIn('Purchases',advanced)

    def test_details_only_copy_and_advanced_not_duplicate_primary_metrics(self):
        app=AppTest.from_string('import ads_meta_review_page as p\nfrom tests.test_meta_review import ad\np.ad_card(ad())').run()
        self.assertFalse(app.exception)
        self.assertTrue(any(e.label=='Advanced metrics' for e in app.expander))
        for frame in app.dataframe:
            self.assertNotIn('ROAS',frame.value.get('Metric',[]).tolist())


class DurableHandoffTests(unittest.TestCase):
    def package(self):
        item=ad()
        selections={k:{**item['assets'][k][0],'ad_id':item['ad_id']} for k in ('image','primary_text','headline')}
        return handoff.build_package(item,selections,{'account_id':'123','campaign_id':'cam','campaign_name':'Exact campaign','market':'AU','format':'INSTANT EXPERIENCE'},'complete_ad')

    def test_image_saved_before_package_and_new_session_hydrates_exact_copy(self):
        package=self.package(); order=[]; saved={}
        def archive(url): order.append('image'); return 'permanent-sha'
        def save(p,actor,action): order.append('package'); saved.update(copy.deepcopy(p)); return 1
        with patch.object(handoff,'archive_image',side_effect=archive),patch.object(store,'save_selection',side_effect=save):
            url=handoff.queue_link(package)
        self.assertEqual(order,['image','package'])
        params={k:v[0] for k,v in parse_qs(urlparse(url).query).items()}
        self.assertEqual(set(params),{'page','handoff_id'})
        self.assertEqual(len(params['handoff_id']),32)
        separate={}
        with patch.object(store,'load_handoff',return_value=saved) as load:
            self.assertTrue(handoff.load_link(separate,params,CONFIG))
            self.assertFalse(handoff.load_link(separate,params,CONFIG))
        load.assert_called_once_with(params['handoff_id'],'act_123')
        import ads_page
        self.assertEqual(separate[ads_page.ADS_CREATIVE_REFRESH_WINNING_PRIMARY_TEXT_KEY],package['components']['primary_text']['value'])
        self.assertEqual(separate[ads_page.ADS_CREATIVE_REFRESH_WINNING_HEADLINE_KEY],package['components']['headline']['value'])
        self.assertEqual(separate[handoff.ACTIVE]['image_sha256'],'permanent-sha')

    def test_archive_failure_never_creates_link_or_handoff(self):
        with patch.object(handoff,'archive_image',side_effect=ValueError('unavailable')),patch.object(store,'save_selection') as save:
            with self.assertRaises(ValueError): handoff.queue_link(self.package())
        save.assert_not_called()

    def test_lookup_validates_token_and_limits_account_and_action(self):
        class Cursor:
            def execute(self,sql,params): self.sql,self.params=sql,params
            def fetchone(self): return {'context':{'image_sha256':'sha'}}
        cursor=Cursor()
        @contextmanager
        def read(): yield cursor
        with patch.object(store,'cursor',read):
            self.assertEqual(store.load_handoff('a'*32,'act_123')['image_sha256'],'sha')
        self.assertIn("action_type='meta_review_handoff'",cursor.sql)
        self.assertIn("context->>'account_id'=%s",cursor.sql)
        self.assertEqual(cursor.params,('a'*32,'123'))
        with patch.object(store,'cursor') as read:
            with self.assertRaises(ValueError): store.load_handoff("' OR 1=1",'123')
        read.assert_not_called()


class WinnerUITests(unittest.TestCase):
    def setUp(self):
        self.patches=[patch.object(page,'_load_preferences',return_value={'selections':[],'mapping':[]}),
                      patch.object(handoff,'queue_link',return_value='?page=creative_refresh&handoff_id='+'a'*32)]
        self.mocks=[p.start() for p in self.patches]
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])
        self.app=AppTest.from_string("import ads_meta_review_page as p\nfrom tests.test_meta_review import history\nh=history()\np.simple_winner(p.build_ads(h),h,{'account_id':'123','campaign_id':'cam'})",default_timeout=10).run()

    def test_automatic_apply_uses_durable_link_not_navigation(self):
        self.assertFalse(self.app.exception)
        button=next(b for b in self.app.button if b.label=='APPLY TO CREATIVE REFRESH')
        self.assertFalse(button.disabled)
        button.click().run()
        self.assertFalse(self.app.exception)
        package=self.mocks[1].call_args.args[0]
        self.assertEqual(package['mode'],'complete_ad')
        self.assertEqual(len(package['components']),3)
        self.assertTrue(self.app.get('link_button'))

    def test_manual_selection_passes_selected_ad_only(self):
        select=next(s for s in self.app.selectbox if s.label=='Winner to use')
        select.select('3').run()
        next(b for b in self.app.button if b.label=='APPLY TO CREATIVE REFRESH').click().run()
        self.assertFalse(self.app.exception)
        package=self.mocks[1].call_args.args[0]
        self.assertEqual(package['ad_id'],'3')
        self.assertTrue(all(c['ad_id']=='3' for c in package['components'].values()))
        self.assertFalse(self.app.multiselect)

    def test_no_automatic_winner_requires_explicit_selection(self):
        with patch.object(page.analysis,'choose_winner',return_value=None):
            self.app.run()
            button=next(b for b in self.app.button if b.label=='APPLY TO CREATIVE REFRESH')
            self.assertTrue(button.disabled)


if __name__=='__main__': unittest.main()
