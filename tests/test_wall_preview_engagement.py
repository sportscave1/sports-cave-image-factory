import unittest,uuid,os
from tests import test_wall_preview_analytics as fixture
import wall_preview_analytics as analytics

class Validation(unittest.TestCase):
    def test_canonical_requires_separate_visit_and_visitor(self):
        payload=fixture.event();payload['event']='wall_preview_open'
        with self.assertRaises(ValueError):analytics.clean(payload)
        payload.update(wall_preview_session_id=str(uuid.uuid4()),visitor_id=str(uuid.uuid4()),active_seconds=1.25)
        self.assertEqual(analytics.clean(payload)['active_seconds'],1.25)
        for invalid in (-1,float('nan'),float('inf'),86401,'12'):
            payload['active_seconds']=invalid
            with self.assertRaises(ValueError):analytics.clean(payload)

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Local PostgreSQL required')
class Database(unittest.TestCase):
    setUpClass=classmethod(lambda cls: fixture.Database.setUpClass())
    setUp=fixture.Database.setUp
    tearDown=fixture.Database.tearDown
    def send(self,name,visit,visitor,active=0,**extra):
        payload=fixture.event();payload.update(event='wall_preview_'+name,session_id=self.data['session_id'],
            wall_preview_session_id=visit,visitor_id=visitor,active_seconds=active)
        payload.update(extra);analytics.ingest(payload);return payload
    def test_capture_rotation_retry_and_cumulative_time(self):
        visit,visitor=str(uuid.uuid4()),str(uuid.uuid4())
        self.send('cta_click',visit,visitor,capture_source='')
        self.send('open',visit,visitor,capture_source='')
        self.send('photo_loaded',visit,visitor)
        self.send('placement_confirmed',visit,visitor)
        self.send('placement_confirmed',visit,visitor) # new capture ID, same visit
        payload=self.send('active_time',visit,visitor,15)
        self.assertFalse(analytics.ingest(payload))
        self.send('active_time',visit,visitor,30)
        self.send('active_time',visit,visitor,12) # out of order cannot lower/double time
        self.send('add_to_cart',visit,visitor)
        self.send('close',visit,visitor,35)
        data=analytics.report({'capture_source':'camera','device_type':'mobile','product_id':'123'})['engagement']
        for key in ('cta_clicks','unique_clickers','opens','photo_ready','confirmed','atc'):
            self.assertEqual(data[key],1,key)
        self.assertEqual(float(data['avg_active_seconds']),35)
        self.assertEqual(float(data['median_active_seconds']),35)
        self.assertEqual(data['click_open_percent'],100)
        self.assertEqual(data['placement_percent'],100)
        self.assertEqual(analytics.report({'device_type':'desktop'})['engagement']['opens'],0)
    def test_failed_open_and_legacy_not_inferred(self):
        visitor=str(uuid.uuid4())
        first=str(uuid.uuid4());self.send('cta_click',first,visitor)
        second=str(uuid.uuid4());self.send('cta_click',second,visitor);self.send('open',second,visitor)
        self.send('close',second,visitor,10)
        fixture.Database.track(self,'Confirmed')
        data=analytics.report()['engagement']
        self.assertEqual(data['cta_clicks'],2);self.assertEqual(data['unique_clickers'],1)
        self.assertEqual(data['click_open_percent'],50);self.assertEqual(data['confirmed'],0)
    def test_visit_cannot_change_owner(self):
        visit,visitor=str(uuid.uuid4()),str(uuid.uuid4())
        self.send('open',visit,visitor)
        with self.assertRaises(PermissionError):self.send('close',visit,str(uuid.uuid4()))

    def test_average_median_and_date_exclusion(self):
        from datetime import datetime,timezone,timedelta
        for seconds in (10,20,90):
            visit,visitor=str(uuid.uuid4()),str(uuid.uuid4())
            self.send('open',visit,visitor);self.send('close',visit,visitor,seconds)
        stats=analytics.report()['engagement']
        self.assertEqual(float(stats['avg_active_seconds']),40)
        self.assertEqual(float(stats['median_active_seconds']),20)
        end=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
        start=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        self.assertEqual(analytics.report({'start_date':start,'end_date':end})['engagement']['opens'],0)
