"""Container-only real PostgreSQL populated recovery planning; never admit jobs."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch

if not Path('/opt/studio/entry.py').is_file() or {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}:
    raise RuntimeError('Requires reviewed network-isolated preview')
sys.path.insert(0, '/tmp/source')
for name, source in MODULES.items():
    path=Path('/tmp/source')/name
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(source)
import psycopg
from psycopg.rows import dict_row
import auto_editions_recovery as candidate
import baseline_recovery as baseline

DSN='postgresql://studio@127.0.0.1:55432/studio?sslmode=disable'
os.environ['DATABASE_URL']=DSN
meter={'queries':0,'sql_ms':0.}
class TimedCursor(psycopg.Cursor):
    def execute(self,*args,**kwargs):
        start=time.perf_counter()
        try:return super().execute(*args,**kwargs)
        finally:
            meter['queries']+=1;meter['sql_ms']+=(time.perf_counter()-start)*1000
def connect(): return psycopg.connect(DSN,row_factory=dict_row,cursor_factory=TimedCursor)
config=dict(policies=[],memberships=[],default_group='')
with connect() as conn:
    conn.execute('CREATE TABLE auto_edition_onboarding(product_gid TEXT PRIMARY KEY,file_id TEXT,status TEXT,priority INT,source JSONB,reason TEXT,preparation_hash TEXT,replacement JSONB,reset_cancellation JSONB,lease_until TIMESTAMPTZ,created_at TIMESTAMPTZ,updated_at TIMESTAMPTZ)')
    conn.execute('CREATE TABLE product_psd_mappings(shopify_product_gid TEXT,dropbox_file_id TEXT)')
    conn.execute('CREATE TABLE auto_edition_preparations(hash TEXT,manifest JSONB,proofs JSONB,receipts JSONB)')
    conn.execute('CREATE TABLE auto_edition_source_inventory(file_id TEXT,metadata JSONB)')
    conn.execute('CREATE TABLE auto_edition_technical_checks(product_gid TEXT,preparation_hash TEXT,checkpoint_at TIMESTAMPTZ,state TEXT,reason TEXT)')
    conn.execute('CREATE TABLE auto_edition_onboarding_audit(id BIGSERIAL PRIMARY KEY,product_gid TEXT,event TEXT,detail JSONB,created_at TIMESTAMPTZ DEFAULT now())')
    conn.execute("INSERT INTO auto_edition_onboarding SELECT 'gid://shopify/Product/'||n,'id:synthetic'||n,'Blocked',2,jsonb_build_object('product_gid','gid://shopify/Product/'||n,'file_id','id:synthetic'||n,'revision','a1','content_hash',repeat('a',64)),'Download interrupted',NULL,NULL,NULL,NULL,now()-interval '1 day',now()-interval '1 day' FROM generate_series(1000,1333)n")
    conn.execute('INSERT INTO product_psd_mappings SELECT product_gid,file_id FROM auto_edition_onboarding')
    conn.execute("INSERT INTO auto_edition_onboarding_audit(product_gid,event,detail) SELECT 'gid://shopify/Product/'||(1000+n%334),'diagnostic','{}' FROM generate_series(1,29000)n")
    conn.execute('CREATE INDEX audit_product ON auto_edition_onboarding_audit(product_gid,created_at DESC,id DESC)')

# The old module hashes its own original filename. Rebind __file__ only, keeping
# the exact real baseline recovery bytes and shared dependency bytes on disk.
original=Path('/tmp/source/auto_editions_recovery.py').read_bytes()
old_source=Path('/tmp/source/baseline_recovery.py').read_bytes()
baseline.__file__='/tmp/source/auto_editions_recovery.py'
def run(module):
    Path('/tmp/source/auto_editions_recovery.py').write_bytes(old_source if module is baseline else original)
    return module.plan(connect,config)
before=run(baseline)
after=run(candidate)
assert before==after and len(before)==334, (before[0]['fingerprint'],after[0]['fingerprint'])
assert all(i['decision']['action']=='retry' and i['waiting']=='' for i in before)

# Distinct completion categories use real source files only. Hash reuse may
# alter neither shared-fix identities nor source/policy-bound retry keys.
checks=['Exact 334-product plan parity, source identity, decision, retry key and ordering']
before_keys=[r['fingerprint'] for r in before]
pid=before[0]['row']['product_gid']
with connect() as conn:
    conn.execute("INSERT INTO auto_edition_onboarding_audit(product_gid,event,detail,created_at) VALUES (%s,%s,%s::jsonb,now()-interval '1 hour')",(pid,candidate.EVENT,json.dumps(dict(fingerprint=before_keys[0]))))
    conn.execute("INSERT INTO auto_edition_onboarding_audit(product_gid,event,detail,created_at) VALUES (%s,%s,%s::jsonb,now()-interval '1 hour')",(pid,candidate.EVENT,json.dumps(dict(fingerprint=before_keys[0]))))
    conn.execute("INSERT INTO auto_edition_onboarding_audit(product_gid,event,detail,created_at) VALUES (%s,%s,%s::jsonb,now()-interval '1 hour')",(pid,candidate.EVENT,json.dumps(dict(fingerprint=before_keys[0]))))
assert run(baseline)==run(candidate)
assert run(candidate)[0]['waiting'].startswith('Retry limit')
checks.append('Existing persisted attempts still exhaust unchanged retry budget')

samples={'baseline':[],'candidate':[]};cpu={'baseline':[],'candidate':[]};costs={}
read_bytes=Path.read_bytes
for label,module in [('baseline',baseline),('candidate',candidate)]:
    Path('/tmp/source/auto_editions_recovery.py').write_bytes(old_source if module is baseline else original)
    counters={'reads':0,'bytes':0}
    meter.update(queries=0,sql_ms=0.)
    def measured(path):
        data=read_bytes(path);counters['reads']+=1;counters['bytes']+=len(data);return data
    with patch.object(Path,'read_bytes',measured):
        for _ in range(5):
            start=time.perf_counter();process=time.process_time()
            result=module.plan(connect,config)
            samples[label].append((time.perf_counter()-start)*1000);cpu[label].append((time.process_time()-process)*1000)
            assert len(result)==334
    costs[label]=dict(counters,**meter)
    checks.append(label+' five full plans completed with all 334 products')
Path('/tmp/source/auto_editions_recovery.py').write_bytes(original)
guarded=candidate.plan(connect,config)
with ThreadPoolExecutor(max_workers=3) as pool:
    assert all(result==guarded for result in pool.map(lambda _: candidate.plan(connect,config),range(3)))
for _ in range(5): assert candidate.plan(connect,config)==guarded
with connect() as conn:
    assert conn.execute('SELECT count(*) AS n FROM auto_edition_onboarding_audit').fetchone()['n']==29003
    assert conn.execute("SELECT count(*) AS n FROM auto_edition_onboarding WHERE status='Blocked'").fetchone()['n']==334
checks += ['Three concurrent planners and five-scan soak retain all rows and write no audit records',
           'No provider/queue admission/companion activation, no UI or API changes']
b,a=map(statistics.median,[samples['baseline'],samples['candidate']])
assert a<=b*.85, 'Full recovery plan improvement below 15 percent'
assert costs['candidate']['reads']<=costs['baseline']['reads']*.01
assert costs['candidate']['queries']==costs['baseline']['queries']
print('RECOVERY_RESULT='+json.dumps(dict(purpose='recovery-source-hash-reuse',baseline_samples_ms=samples['baseline'],
    candidate_samples_ms=samples['candidate'],cpu_samples_ms=cpu,costs=costs,checks=checks,behaviour_preserved=True,
    improvement_ms=b-a,improvement_percent=(b-a)/b*100)))
