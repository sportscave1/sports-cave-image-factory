import copy
from datetime import date
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import ads_meta_review_page as page
import meta_review_search as search
import meta_review_tables as tables
from tests.test_meta_review_live import CONFIG

ROWS=[{'campaign_id':str(i),'campaign_name':name,'status':status,'start_time':f'2026-09-{20+i:02d}','metrics':{'spend':i*10}} for i,(name,status) in enumerate([
 ('290926 AUS Motorsport Peter Brock Tribute','ACTIVE'),('290926 USA Baseball The Rivalry Jeter vs Ortiz','PAUSED'),
 ('280926 UK Tennis Eternal Rivals Federer vs Nadal','ACTIVE'),('Peter Brock','PAUSED'),('Brock Legends','ACTIVE'),
 ('Brock Racing','ACTIVE'),('Brock Poster','ACTIVE'),('Brock Classic','ACTIVE')])]

class SearchTests(unittest.TestCase):
    def test_calendar_year_and_leap_day(self):
        self.assertEqual(search.reporting_default(date(2026,9,30)),(date(2025,9,30),date(2026,9,30)))
        self.assertEqual(search.reporting_default(date(2024,2,29))[0],date(2023,2,28))
    def test_search_examples_and_fuzzy(self):
        for query,expected in [('JETER   ort','1'),('feder nad','2'),('petr brok','3'),('PETER---BROCK','3')]:
            self.assertEqual(search.search_campaigns(ROWS,query)[0]['campaign_id'],expected)
        self.assertEqual(len(search.search_campaigns(ROWS,'brock')),5)
    def test_exact_title_wins(self):
        self.assertEqual(search.search_campaigns(ROWS,ROWS[0]['campaign_name'])[0],ROWS[0])
    def test_clear_sort_markets_and_no_mutation(self):
        before=copy.deepcopy(ROWS)
        default=tables.sort_campaigns(ROWS)
        self.assertEqual(default[0]['status'],'ACTIVE')
        explicit=tables.sort_campaigns(ROWS,'Spend')
        self.assertEqual(search.search_campaigns(explicit,''),explicit)
        self.assertEqual(len(search.search_campaigns(ROWS,'')),len(ROWS))
        search.search_campaigns(ROWS,'brock')
        self.assertEqual(ROWS,before)
        paused={'campaign_id':'high','status':'PAUSED','metrics':{'spend':999}}
        self.assertEqual(tables.sort_campaigns([*ROWS,paused],'Spend')[0],paused)
    def test_ui_actions_reuse_loaded_data_refresh_fetches(self):
        data={'account':{'name':'Sports Cave','currency':'AUD'},'campaigns':copy.deepcopy(ROWS)}
        with patch.object(page.meta,'get_meta_config',return_value=CONFIG),patch.object(page.live,'load_overview',return_value=data) as load,patch.object(page.recency,'load',return_value={'available':False}),patch.object(page,'campaign_popup') as popup:
            app=AppTest.from_string('import ads_meta_review_page as p\np.render_page()').run()
            self.assertFalse(app.exception)
            app.text_input[0].set_value('jeter ort').run()
            self.assertEqual(len(app.dataframe[0].value),1)
            app.text_input[0].set_value('').run()
            self.assertEqual(len(app.dataframe[0].value),len(ROWS))
            app.selectbox[0].select('Spend').run()
            self.assertEqual(load.call_count,1)
            popup.assert_not_called()
            app.button[0].click().run()
            self.assertEqual(load.call_count,2)
            self.assertFalse(app.exception)

if __name__=='__main__':unittest.main()
