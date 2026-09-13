import copy
from datetime import timedelta
import unittest
import meta_review_tables as tables
import meta_review_recency as recency
from tests.test_meta_review_va import NOW,evidence


class ExpandedSortTests(unittest.TestCase):
    def test_every_metric_direction_missing_last_and_explicit_zero(self):
        for label,(field,ascending) in tables.SORT_METRICS.items():
            rows=[]
            for i,value in enumerate((None,9,0,2,'—',float('nan'))):
                row={'campaign_id':str(i),'metrics':{},'benchmark':{}}
                row['benchmark' if field=='score' else 'metrics'][field]=value
                rows.append(row)
            before=copy.deepcopy(rows)
            with self.subTest(label=label):
                result=tables.sort_campaigns(rows,label)
                self.assertEqual([r['campaign_id'] for r in result[:3]],['2','3','1'] if ascending else ['1','3','2'])
                self.assertEqual({r['campaign_id'] for r in result[3:]},{'0','4','5'})
                self.assertEqual(rows[1],before[1])

    def test_ctr_and_link_ctr_are_distinct_fields(self):
        rows=[{'campaign_id':'1','metrics':{'click_ctr':9,'ctr':1}},
              {'campaign_id':'2','metrics':{'click_ctr':1,'ctr':9}}]
        self.assertEqual(tables.sort_campaigns(rows,'CTR')[0]['campaign_id'],'1')
        self.assertEqual(tables.sort_campaigns(rows,'Link CTR')[0]['campaign_id'],'2')

    def test_last_sale_uses_evidence_not_display_text(self):
        rows=[]
        for identity,hours in [('a',31),('b',2),('c',19),('d',8),('e',60)]:
            row={'campaign_id':identity,'status':'ACTIVE','metrics':{'purchases':1}}
            ev=evidence(hours); ev['latest'][identity]=ev['latest'].pop('1')
            row['recency']=recency.signal(row,ev,NOW)
            row['recency']['text']='This text must never control sorting'
            rows.append(row)
        rows += [
            {'campaign_id':'old','recency':{'sale_sort_state':'older'}},
            {'campaign_id':'unknown','recency':{'text':'2h ago'}},
            {'campaign_id':'no-old','recency':{'sale_sort_state':'no_sale'},'start_time':(NOW-timedelta(hours=31)).isoformat()},
            {'campaign_id':'no-new','recency':{'sale_sort_state':'no_sale'},'start_time':(NOW-timedelta(hours=14)).isoformat()}]
        self.assertEqual([r['campaign_id'] for r in tables.sort_campaigns(rows,'Last Sale')],
                         ['b','d','c','a','e','old','no-new','no-old','unknown'])

    def test_unavailable_or_stale_evidence_has_no_sale_sort_timestamp(self):
        row={'campaign_id':'1','metrics':{'purchases':1}}
        self.assertNotIn('sale_sort_timestamp',recency.signal(row,{'available':False},NOW))
        self.assertNotIn('sale_sort_timestamp',recency.signal(row,evidence(2),NOW+timedelta(minutes=4)))

    def test_newest_start_creation_fallback_and_deterministic_ties(self):
        rows=[{'campaign_id':'missing'}, {'campaign_id':'created','created_time':'2026-09-12'},
              {'campaign_id':'older','start_time':'2026-09-01','created_time':'2026-09-13'},
              {'campaign_id':'new','start_time':'2026-09-13'}]
        self.assertEqual([r['campaign_id'] for r in tables.sort_campaigns(rows)],['new','created','older','missing'])
        self.assertEqual(tables.SORT_OPTIONS[0],'Newest')
        self.assertEqual(len(tables.SORT_OPTIONS),32)
        self.assertEqual(len(set(tables.SORT_OPTIONS)),32)


if __name__=='__main__': unittest.main()
