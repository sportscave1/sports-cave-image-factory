"""Opt-in localhost benchmark; invoke through run_email_reliability.py.

No production connector, recipients, or provider is used. Set EMAIL_V4_PHASE to
label baseline/after output. Timings are localhost measurements, not SLO claims.
"""
import json
import math
import os
from pathlib import Path
from time import perf_counter, process_time
import tracemalloc
from copy import deepcopy
from unittest.mock import patch
from tests.test_crm_automation_publication import PublicationTests, ADMIN, LIVE


class Measurements(PublicationTests):
    def test_measure(self):
        from crm_automation_definition import email_step
        from crm_automation_publication import prepare
        from crm_automation_publish_state import has_changes
        from crm_email_editor_context import flush_automation
        metrics={}
        def measure(name, call):
            start=perf_counter();result=call()
            metrics.setdefault(name,[]).append((perf_counter()-start)*1000)
            return result
        tracemalloc.start();cpu=process_time()
        for count in (1,3,6):
            for sample in range(12):
                row=self.draft('abandoned');flow=deepcopy(row['config']['draft'])
                flow['emails']=[email_step(flow['emails'][0]['document'],600*(i+1)) for i in range(count)]
                row=self.store.save_flow(ADMIN,row['id'],row['name'],flow,row['config']['revision'])
                prefix=str(count)+'_emails/'
                measure(prefix+'accept',lambda:self.job(row))
                with patch('crm_automation_publication.prepare',side_effect=lambda *a,**kw:measure(prefix+'validate',lambda:prepare(*a,**kw))):
                    measure(prefix+'worker',self.run_job)
                row=measure(prefix+'readback',lambda:self.state(row))
                measure(prefix+'compare',lambda:has_changes(self.store,row))
                measure(prefix+'no_change_publish',lambda:self.job(row))
                self.store.step_id=flow['emails'][0]['step_id']
                editor=self.store.draft(row['id'],row=row)
                state={'automation_editor':editor,'automation_saved':deepcopy(editor),'automation_editor_context':(self.store,ADMIN)}
                with patch.object(self.store,'save',wraps=self.store.save) as save:
                    measure(prefix+'unchanged_save',lambda:flush_automation(state,force=True))
                    metrics.setdefault(prefix+'unchanged_save_calls',[]).append(save.call_count)
        peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
        result={'scope':'isolated loopback PGlite; tracemalloc enabled; 12 independent samples per email count',
                'cpu_seconds':process_time()-cpu,'peak_python_bytes':peak,'metrics':{}}
        for key,values in metrics.items():
            ordered=sorted(values)
            result['metrics'][key]={'n':len(values),'p50':round(ordered[len(values)//2],3),'p95':round(ordered[math.ceil(.95*len(values))-1],3)}
        destination=Path('tmp')/('email_v4_'+os.environ.get('EMAIL_V4_PHASE','baseline')+'.json')
        destination.write_text(json.dumps(result,indent=2),encoding='utf8')
        print(destination, json.dumps(result))
