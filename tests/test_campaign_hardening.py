import unittest
from datetime import time
from crm_campaign_schedule import recipient_zone,resolve

class TimezoneEvidenceTests(unittest.TestCase):
    def test_darwin_requires_consistent_address(self):
        row={'defaultAddress':{'countryCodeV2':'AU','provinceCode':'NT','zip':'0800','timeZone':'Australia/Darwin'}}
        self.assertEqual(recipient_zone(row),('Australia/Darwin','validated_address_timezone'))
        row['defaultAddress']['zip']='2000'
        with self.assertRaisesRegex(ValueError,'conflicting_recipient_postcode'):recipient_zone(row)
        self.assertEqual(resolve(row),('Australia/Darwin','address_timezone'))

    def test_country_and_state_contradictions(self):
        for address in ({'countryCodeV2':'AU','country':'United Kingdom','provinceCode':'NT'},
                        {'countryCodeV2':'AU','provinceCode':'NT','province':'New South Wales'},
                        {'countryCodeV2':'AU','provinceCode':'NT','zip':'2880'},
                        {'countryCodeV2':'AU','provinceCode':'NSW','zip':'2880','timeZone':'Australia/Sydney'}):
            with self.subTest(address=address),self.assertRaisesRegex(ValueError,'conflicting'):recipient_zone({'defaultAddress':address})

    def test_no_customer_country_or_timezone_fallback(self):
        for row in ({'country':'AU','defaultAddress':{'provinceCode':'NT'}},
                    {'timezone':'Australia/Darwin'}, {'defaultAddress':{}},
                    {'defaultAddress':{'countryCodeV2':'AU','provinceCode':'NT','timeZone':'Australia/Darwin'}}):
            with self.subTest(row=row),self.assertRaises(ValueError):recipient_zone(row)

    def test_broken_hill_and_ambiguous_postcodes(self):
        self.assertEqual(recipient_zone({'defaultAddress':{'countryCodeV2':'AU','provinceCode':'NSW','zip':'2880'}})[0],'Australia/Broken_Hill')
        for postcode in ('0872','6443','not a postcode'):
            with self.subTest(postcode=postcode),self.assertRaises(ValueError):recipient_zone({'defaultAddress':{'countryCodeV2':'AU','provinceCode':'NT','zip':postcode}})

    def test_legacy_provenance_cannot_distinguish_customer_timezone(self):
        self.assertEqual(resolve({'timezone':'Australia/Darwin'}),('Australia/Darwin','address_timezone'))
        self.assertEqual(resolve({}),('UTC','global_utc_fallback'))
        self.assertEqual(resolve({'defaultAddress':{'timeZone':'Europe/London'}}),('Europe/London','address_timezone'))


class DetailReadTests(unittest.TestCase):
    def setUp(self):
        # AppTest executes this synthetic browser fixture in-process. Restore
        # its mocked services so ordinary unittest discovery stays isolated.
        from unittest.mock import patch
        import requests
        import crm_campaign_schedule as schedule
        import crm_campaign_home as home
        import crm_campaign_home_progress as progress
        import crm_email_diagnostics as diagnostics
        for target,name in ((schedule,'change_pending'),(home,'_job'),(progress,'job'),
                            (diagnostics,'campaign_status'),(requests.sessions.Session,'request')):
            guard=patch.object(target,name,getattr(target,name));guard.start();self.addCleanup(guard.stop)

    def test_detail_reads_progress_once_and_defers_dialog_context(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file('tests/fixtures/campaign_hardening_preview.py',default_timeout=30).run()
        self.assertFalse(app.exception)
        counts=app.session_state['fixture-counts']
        self.assertEqual(counts['queries'],1)
        self.assertEqual(counts['states'],0)
        self.assertEqual(counts['templates'],0)

    def test_dialog_field_changes_reuse_opening_revision_context(self):
        from streamlit.testing.v1 import AppTest
        app=AppTest.from_file('tests/fixtures/campaign_hardening_preview.py',default_timeout=30).run()
        next(b for b in app.button if b.label=='Edit schedule').click().run()
        self.assertFalse(app.exception)
        reads=app.session_state['fixture-counts']['states']
        next(t for t in app.time_input if t.label=='Time').set_value(time(18)).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['fixture-counts']['states'],reads)
        self.assertEqual(app.session_state['fixture-counts']['amendments'],0)
