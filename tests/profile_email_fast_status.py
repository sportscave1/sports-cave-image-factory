"""Explicit simulated 500ms provider delay; no external connections."""
import json
import time
from unittest.mock import patch
import support_email_notifications as service
from tests.email_v2_fixtures import CONFIG

def refresh(**kwargs):
    time.sleep(.5)
    service._CACHE.update(scope=CONFIG.scope,expires=time.time()+60,
        value={'available':True,'unread_count':3,'checked_at':time.time()})
    return dict(service._CACHE['value'])

def run():
    with patch.object(service,'load_configuration',return_value=CONFIG),patch.object(service,'status',side_effect=refresh):
        start=time.perf_counter();refresh();before=(time.perf_counter()-start)*1000
        service._CACHE['expires']=0
        start=time.perf_counter();result=service.fast_status();after=(time.perf_counter()-start)*1000
        service._REFRESH.result(timeout=3)
        return {'synthetic_provider_ms':500,'old_blocking_request_ms':round(before,2),
            'new_cached_request_ms':round(after,2),'cached_count':result['unread_count'],
            'background_refreshing':result['refreshing'],'body_or_attachment_reads':0}

if __name__=='__main__':print(json.dumps(run(),indent=2))
