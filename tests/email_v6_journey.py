"""Comparable local database/render/publication measurements, no live systems."""
from copy import deepcopy
import json
import os
from pathlib import Path
from time import perf_counter
import unittest
from unittest.mock import patch,Mock
from tests.test_crm import ADMIN
from tests.test_crm_send_flow import LIVE

@unittest.skipUnless(os.getenv('CRM_TEST_POSTGRES')=='1','Disposable PostgreSQL required')
class JourneyBenchmark(unittest.TestCase):
    def test_local_journey(self):
        from tests.test_crm_automation_publication import PublicationTests
        from crm_campaign_content import preflight
        fixture=PublicationTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        rows=[];fixture.store.preview_shop=Mock()
        with patch('crm_thumbnail_cache.prewarm'),patch('streamlit.session_state',{}):
            row=fixture.draft('abandoned')
            for i in range(12):
                record={}
                def measured(key,fn):
                    start=perf_counter();result=fn();record[key]=(perf_counter()-start)*1000;return result
                row=measured('reopen_database_ms',lambda:fixture.store.flow(row['id']))
                flow=deepcopy(row['config']['draft']);flow['emails'][0]['document']['content']['subject']='Local measured creative '+str(i)
                row=measured('draft_save_database_ms',lambda:fixture.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision']))
                doc=flow['emails'][0]['document']
                preview=measured('safe_preview_backend_ms',lambda:fixture.store.preview_document(doc)[0])
                measured('readiness_backend_ms',lambda:preflight(preview,LIVE,fixture.store.render_settings()))
                measured('publish_request_database_ms',lambda:fixture.job(row))
                measured('publication_worker_ms',fixture.run_job)
                ready=measured('publication_readback_database_ms',lambda:fixture.state(row))
                self.assertEqual(ready['config']['publication']['state'],'LIVE')
                record['request_to_verified_local_live_ms']=sum(record[k] for k in ('publish_request_database_ms','publication_worker_ms','publication_readback_database_ms'))
                rows.append(record)
            self.assertEqual(fixture.store.q('SELECT count(*)::int AS total FROM crm_marketing_sends',one=True)['total'],0)
        path=Path('tmp/email-v6-'+os.getenv('EMAIL_V6_LABEL','after')+'-journey.json')
        path.write_text(json.dumps(rows,indent=2),encoding='utf8')
