"""Opt-in save benchmark against the runner's disposable SQL fixture."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import statistics
from time import perf_counter,process_time
import tracemalloc
import unittest
from unittest.mock import patch

class SaveMeasurements(unittest.TestCase):
    def test_measure(self):
        from tests.crm_db_fixture import connect
        from tests.test_crm import ADMIN
        from tests.test_crm_simple_editor import document
        from crm_campaign_store import CampaignStore
        from crm_campaign_recovery import flush_current
        import crm_campaign_recovery
        store=CampaignStore(connect);store.seed();values={'unchanged_ms':[],'modified_ms':[]}
        tracemalloc.start();cpu=process_time()
        for sample in range(24):
            editor=store.save(ADMIN,'Performance save fixture',document())
            state={'campaign_editor':editor,'campaign_saved':deepcopy(editor),'campaign_recovery_context':(store,ADMIN)}
            with patch('streamlit.session_state',state),patch('streamlit.query_params',{}),patch('crm_campaign_recovery.save_checkpoint',wraps=crm_campaign_recovery.save_checkpoint) as save:
                start=perf_counter();self.assertTrue(flush_current(force=True));values['unchanged_ms'].append((perf_counter()-start)*1000)
                save.assert_not_called()
                old_version=editor['version'];editor['document']['content']['subject']+=' changed'
                start=perf_counter();self.assertTrue(flush_current(force=True));values['modified_ms'].append((perf_counter()-start)*1000)
                save.assert_called_once();self.assertEqual(editor['version'],old_version+1)
                saved=store.draft(editor['id']);self.assertEqual(saved['document'],editor['document'])
                self.assertTrue(flush_current(force=True));save.assert_called_once()
        peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
        result={'scope':'24 independent local SQL Campaign save samples; tracing enabled; no UI/network latency',
                'cpu_seconds':process_time()-cpu,'peak_python_bytes':peak,'samples':values,
                'metrics':{k:{'n':len(v),'p50':statistics.median(v),'p95':sorted(v)[math.ceil(.95*len(v))-1]} for k,v in values.items()}}
        Path('tmp/email-v5-saves-'+os.getenv('EMAIL_V5_LABEL','after')+'.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
