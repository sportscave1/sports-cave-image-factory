"""Fixture-only timing probe; excludes real DNS/TLS/network/Postgres latency."""
import json
from statistics import mean
from time import perf_counter
from unittest.mock import patch
import support_email_notifications as service
from support_email_provider import ImapProvider
from tests.test_support_email_notifications import NotificationWire, MemoryDatabase
from tests.email_v2_fixtures import CONFIG


def measure():
    wire=NotificationWire();db=MemoryDatabase()
    adapter=ImapProvider(CONFIG,connection_factory=lambda *a,**k:wire)
    store=service.NotificationStore()
    samples=[]
    with patch('supabase_backend.connect',db.connect):
        store.poll(adapter,now=1000)
        wire.calls.clear()
        for i in range(50):
            start=perf_counter();store.poll(adapter,now=1031+i*31)
            samples.append((perf_counter()-start)*1000)
        commands=wire.calls[:3]
        service._CACHE.update(scope=None,expires=0,success=0,value={})
        service.status(configuration=CONFIG,provider=adapter,store=store,now=5000)
        cached=[];wire.calls.clear()
        for _ in range(100):
            start=perf_counter();service.status(configuration=CONFIG,provider=adapter,store=store,now=5001)
            cached.append((perf_counter()-start)*1000)
    return {'fixture_only':True,'unchanged_checks':len(samples),'average_check_ms':round(mean(samples),3),
            'cached_check_ms':round(mean(cached),4),'commands_per_uncached_check':commands,
            'cached_imap_calls':len(wire.calls),'body_fetches':0,'attachment_fetches':0}


if __name__=='__main__':print(json.dumps(measure(),indent=2))
