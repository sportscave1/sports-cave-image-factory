"""Populated real PostgreSQL Human Work diagnosis in the reviewed Docker boundary."""
from pathlib import Path
import os
import sys
import json
import time
import statistics
import cProfile
import pstats
from datetime import date
from zoneinfo import ZoneInfo
from unittest.mock import patch
from contextlib import contextmanager

if not Path('/opt/studio/entry.py').is_file() or {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}:
    raise RuntimeError('Requires reviewed isolated preview')
sys.path.insert(0, '/tmp/source')
for name, source in MODULES.items():
    Path('/tmp/source', name).write_text(source)
DSN='postgresql://studio@127.0.0.1:55432/studio?sslmode=disable'
os.environ['DATABASE_URL']=DSN
os.environ['SPORTS_CAVE_ADMIN_EMAIL']='preview@example.invalid'
import psycopg
import baseline_backend
import supabase_backend
import baseline_dashboard
import sports_cave_dashboard
USER=dict(id='report-owner',email='preview@example.invalid',role='admin',is_active=True,
          account_status='active',page_permissions=['reporting'],timezone='Australia/Sydney')
START=END=date(2026,11,26)
with psycopg.connect(DSN) as conn:
    conn.execute('''CREATE TABLE human_work_events(id UUID PRIMARY KEY,user_id TEXT,staff_display_name TEXT,
        staff_role TEXT,origin TEXT,area TEXT,action_type TEXT,description TEXT,entity_type TEXT,entity_id TEXT,
        source_route TEXT,outcome TEXT,occurred_at TIMESTAMPTZ,actual_seconds INT,correlation_key TEXT,
        metadata JSONB,audit_log_id BIGINT,created_at TIMESTAMPTZ)''')
    conn.execute('''INSERT INTO human_work_events
        SELECT md5(n::text)::uuid, CASE WHEN n%3=0 THEN 'other-owner' ELSE 'report-owner' END,
        CASE WHEN n%3=0 THEN 'Synthetic Other' ELSE 'Synthetic Owner' END,'admin','human',
        CASE WHEN n%2=0 THEN 'Orders' ELSE 'Designs' END,'review','Synthetic work '||n,'product',n::text,
        '/reporting',CASE WHEN n%4=0 THEN 'failed' ELSE 'completed' END,
        '2026-11-26 01:00:00+00'::timestamptz+n*interval '1 second',120,'synthetic:'||n,
        '{}'::jsonb,NULL,'2026-11-26 01:00:00+00'::timestamptz+n*interval '1 second'
        FROM generate_series(1,6000) n''')
    conn.execute('CREATE INDEX ON human_work_events(occurred_at DESC)')
    conn.execute('ANALYZE human_work_events')

METER={}
class ReadCursor(psycopg.Cursor):
    def execute(self,query,params=None,**kwargs):
        assert isinstance(query,str) and query.lstrip().upper().startswith(('SELECT','SET LOCAL','SHOW')), 'Reader wrote data'
        start=time.perf_counter()
        try:return super().execute(query,params,**kwargs)
        finally:
            METER['queries']+=1
            METER['sql_ms']+=(time.perf_counter()-start)*1000

def configure(module):
    module.ensure_dashboard_schema=lambda:None
    name='read_connection' if module is supabase_backend else 'connect'
    original=getattr(module,name)
    @contextmanager
    def measured():
        start=time.perf_counter()
        with original() as conn:
            METER['acquisitions']+=1
            METER['acquisition_ms']+=(time.perf_counter()-start)*1000
            conn.cursor_factory=ReadCursor
            yield conn
    setattr(module,name,measured)

for module in (baseline_backend,supabase_backend):configure(module)
def run(dashboard,backend,**kwargs):
    with patch.object(dashboard,'get_supabase_backend',return_value=backend):
        return dashboard.list_human_work_entries_page(START,END,user=USER,**kwargs)

# Reproduce shipped failure without concealing it in timing samples.
failures=[]
for _ in range(3):
    try:run(baseline_dashboard,baseline_backend)
    except baseline_dashboard.DashboardStorageError as error:
        assert isinstance(error.__cause__,NameError) and 'ZoneInfo' in str(error.__cause__)
        failures.append(type(error.__cause__).__name__)
    else:raise AssertionError('Expected deployed failure did not reproduce')
# Diagnostic working baseline: repair missing import ONLY to measure intended reader.
# This is not represented as successful deployed baseline performance.
baseline_dashboard.ZoneInfo=ZoneInfo
assert hasattr(sports_cave_dashboard,'ZoneInfo'), 'Candidate must repair the missing import'
samples={};costs={};cpu={}
for label,dashboard,backend in [('baseline',baseline_dashboard,baseline_backend),('candidate',sports_cave_dashboard,supabase_backend)]:
    samples[label]=[];cpu[label]=[]
    METER.update(queries=0,sql_ms=0.,acquisitions=0,acquisition_ms=0.)
    for _ in range(5):
        start=time.perf_counter();cpu_start=time.process_time()
        result=run(dashboard,backend)
        assert len(result['rows'])==25 and result['has_next']
        samples[label].append((time.perf_counter()-start)*1000)
        cpu[label].append((time.process_time()-cpu_start)*1000)
    costs[label]=dict(METER)
    if label=='candidate':
        import database_read_pool
        costs[label]['new_transports']=sum(item.get('connections_num',0) for item in database_read_pool.stats())
    else:costs[label]['new_transports']=5
profile=cProfile.Profile()
profile.runcall(run,baseline_dashboard,baseline_backend)
pstats.Stats(profile).sort_stats('cumtime').print_stats(18)

checks=['Three exact shipped NameErrors reproduced before DB; performance baseline adds only missing import']
assert costs['baseline']['queries']==costs['candidate']['queries']==10
before=statistics.median(samples['baseline']);after=statistics.median(samples['candidate'])
assert after<before*.8, 'Working-reader improvement below20percent'
reference=run(baseline_dashboard,baseline_backend)
assert reference==run(sports_cave_dashboard,supabase_backend)
for kwargs in [dict(page=2),dict(staff_filter='Other'),dict(area_filter='Orders'),
               dict(action_type_filter='review',outcome_filter='failed'),dict(staff_filter='absent'),
               dict(page_size=100),dict(page=241)]:
    assert run(baseline_dashboard,baseline_backend,**kwargs)==run(sports_cave_dashboard,supabase_backend,**kwargs)
assert run(sports_cave_dashboard,supabase_backend)==reference, 'Stale filtered response'
assert baseline_backend.list_human_work_events(limit=None)==supabase_backend.list_human_work_events(limit=None)
assert len(supabase_backend.list_human_work_events(limit=None))==6000
checks.append('Exact full rows/page/filter/outcome/empty/last-page equality against import-only baseline; no data cache')
with patch.dict(os.environ,SPORTS_CAVE_ADMIN_EMAIL='different@example.invalid'):
    for module,backend in [(baseline_dashboard,baseline_backend),(sports_cave_dashboard,supabase_backend)]:
        value=run(module,backend,staff_filter='Other')
        assert len(value['rows'])==25 and all(row['user_id']==USER['id'] for row in value['rows'])
for module in (baseline_dashboard,sports_cave_dashboard):
    with patch.object(module,'get_supabase_backend',side_effect=AssertionError('Denied user reached DB')):
        try:module.list_human_work_entries_page(START,END,user=dict(USER,is_active=False))
        except module.DashboardStorageError:pass
        else:raise AssertionError('Inactive allowed')
checks.append('Real all-user/own-user scopes; staff filter cannot broaden own read; inactive denial before DB')
# Exercise an actual PostgreSQL statement timeout, then reuse the same transport.
with psycopg.connect(DSN) as lock:
    lock.execute('LOCK human_work_events IN ACCESS EXCLUSIVE MODE')
    with patch.object(supabase_backend,'_dashboard_query_timeout_ms',return_value=60):
        try:run(sports_cave_dashboard,supabase_backend)
        except sports_cave_dashboard.DashboardStorageError as error:
            assert isinstance(error.__cause__,psycopg.errors.QueryCanceled)
        else:raise AssertionError('Timeout not enforced inside pooled transaction')
    lock.rollback()
assert run(sports_cave_dashboard,supabase_backend)==reference
with supabase_backend.read_connection() as conn:
    assert conn.execute('SHOW statement_timeout').fetchone()['statement_timeout']=='8s'
checks.append('Real SQL timeout, rollback/reuse recovery, transaction-local timeout returns to8s default')
from concurrent.futures import ThreadPoolExecutor
with patch.object(sports_cave_dashboard,'get_supabase_backend',return_value=supabase_backend):
    with ThreadPoolExecutor(max_workers=3) as executor:
        assert all(v==reference for v in executor.map(lambda _:sports_cave_dashboard.list_human_work_entries_page(START,END,user=USER),range(9)))
    for _ in range(20):assert sports_cave_dashboard.list_human_work_entries_page(START,END,user=USER)==reference
import database_read_pool
pool_stats=database_read_pool.stats()
assert all(item.get('pool_size',0)<=3 for item in pool_stats)
with supabase_backend.read_connection() as conn:conn.close()
assert run(sports_cave_dashboard,supabase_backend)==reference
checks.append('Nine reads with3threads,20read soak, pool<=3, disconnected transport discarded and next read recovers')
cold={}
for label,module,backend in [('baseline',baseline_dashboard,baseline_backend),('candidate',sports_cave_dashboard,supabase_backend)]:
    cold[label]=[]
    for _ in range(3):
        database_read_pool.close()
        start=time.perf_counter();assert run(module,backend)==reference
        cold[label].append((time.perf_counter()-start)*1000)
# All actual UI queries below use only this private DB. No host app/server.
Path('/tmp/source/human_work_speed_app.py').write_text("""
import os,importlib
from datetime import date
from zoneinfo import ZoneInfo
import streamlit as st
import reporting_page
backend=importlib.import_module('baseline_backend' if os.environ['HUMAN_VARIANT']=='baseline_dashboard' else 'supabase_backend')
backend.ensure_dashboard_schema=lambda:None
target=importlib.import_module(os.environ['HUMAN_VARIANT'])
if os.environ['HUMAN_VARIANT']=='baseline_dashboard':target.ZoneInfo=ZoneInfo
target.get_supabase_backend=lambda:backend
reporting_page.sports_cave_dashboard=target
user=dict(id='report-owner',email='preview@example.invalid',role='admin',is_active=True,account_status='active',timezone='Australia/Sydney',page_permissions=['reporting'])
st.set_page_config(layout='wide')
reporting_page._render_operational_activity(user,date(2026,11,26),date(2026,11,26))
st.caption('Synthetic Human Work ready')
""")
from playwright.sync_api import sync_playwright,expect
import subprocess,urllib.request,hashlib
from PIL import Image,ImageChops
frames=Path('/tmp/human-work-evidence');frames.mkdir()
browser_samples={};interactions={};screenshots={}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,chromium_sandbox=True,args=['--disable-background-networking','--disable-component-update','--num-raster-threads=1','--renderer-process-limit=2'])
    try:
        for label,module in [('baseline','baseline_dashboard'),('candidate','sports_cave_dashboard')]:
            log=open('/tmp/human-work-'+label+'.log','w')
            process=subprocess.Popen([sys.executable,'-B','-m','streamlit','run','/tmp/source/human_work_speed_app.py','--server.address=127.0.0.1','--server.port=8502','--server.headless=true','--server.fileWatcherType=none','--browser.gatherUsageStats=false','--server.disconnectedSessionTTL=5'],env=dict(os.environ,HUMAN_VARIANT=module,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),stdout=log,stderr=subprocess.STDOUT)
            try:
                for attempt in range(100):
                    try:
                        assert urllib.request.urlopen('http://127.0.0.1:8502/_stcore/health',timeout=1).status==200
                        break
                    except Exception:
                        assert process.poll() is None,Path(log.name).read_text()[-2000:]
                        time.sleep(.1)
                context=browser.new_context(viewport=dict(width=1280,height=1000))
                context.route('**/*',lambda route:route.continue_() if route.request.url.startswith('http://127.0.0.1:8502/') else route.abort())
                browser_samples[label]=[];interactions[label]=[]
                for i in range(3):
                    page=context.new_page();start=time.perf_counter()
                    page.goto('http://127.0.0.1:8502/',wait_until='domcontentloaded')
                    page.get_by_text('Synthetic Human Work ready',exact=True).wait_for(timeout=30000)
                    page.locator('[data-testid="stDataFrame"] canvas').first.wait_for()
                    expect(page.get_by_role('button',name='Next',exact=True)).to_be_enabled()
                    browser_samples[label].append((time.perf_counter()-start)*1000)
                    start=time.perf_counter()
                    page.get_by_role('button',name='Next',exact=True).click()
                    page.get_by_text('Page 2 | Up to 25 records per page',exact=True).wait_for()
                    expect(page.get_by_role('button',name='Previous',exact=True)).to_be_enabled()
                    page.get_by_role('textbox',name='Area',exact=True).fill('Orders')
                    page.get_by_role('textbox',name='Area',exact=True).press('Enter')
                    page.get_by_text('Page 1 | Up to 25 records per page',exact=True).wait_for()
                    page.locator('[data-testid="stStatusWidget"]').wait_for(state='hidden')
                    interactions[label].append((time.perf_counter()-start)*1000)
                    assert page.locator('[data-testid="stException"]').count()==0
                    if i==2:
                        for view,width,height in [('desktop',1280,1000),('mobile',390,844)]:
                            page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(500)
                            page.evaluate('document.activeElement?.blur()');page.mouse.move(0,0)
                            page.locator('[data-testid="stStatusWidget"]').wait_for(state='hidden')
                            data=page.screenshot(full_page=True,animations='disabled')
                            (frames/f'{label}-{view}.png').write_bytes(data)
                            screenshots[f'{label}-{view}']=hashlib.sha256(data).hexdigest()
                    page.close()
                tabs=[context.new_page() for _ in range(3)]
                for page in tabs:page.goto('http://127.0.0.1:8502/',wait_until='domcontentloaded')
                for page in tabs:
                    page.get_by_text('Synthetic Human Work ready',exact=True).wait_for()
                    page.get_by_role('textbox',name='Staff member',exact=True).fill('absent')
                    page.get_by_role('textbox',name='Staff member',exact=True).press('Enter')
                    page.get_by_text('No human work records match these filters.',exact=True).wait_for()
                    page.get_by_role('textbox',name='Staff member',exact=True).fill('')
                    page.get_by_role('textbox',name='Staff member',exact=True).press('Enter')
                    page.locator('[data-testid="stDataFrame"] canvas').first.wait_for()
                    assert page.locator('[data-testid="stException"]').count()==0
                context.close()
            finally:process.terminate();process.wait(timeout=15);log.close()
    finally:browser.close()
for view in ['desktop','mobile']:
    b=Image.open(frames/f'baseline-{view}.png').convert('RGB');a=Image.open(frames/f'candidate-{view}.png').convert('RGB')
    assert b.size==a.size
    changed=sum(pixel!=(0,0,0) for pixel in ImageChops.difference(b,a).getdata())
    assert changed<=8,('Visual parity',view,changed)
    screenshots[view+'_changed_pixels']=changed
assert statistics.median(browser_samples['candidate'])<=statistics.median(browser_samples['baseline'])*1.15
assert statistics.median(interactions['candidate'])<=statistics.median(interactions['baseline'])*1.15
checks.append('Actual Chromium3sessions/revision rows usable, next-page and filter reset;3tabs empty->restored; desktop/mobile unmasked<=8pixel parity')
with psycopg.connect(DSN) as conn:assert conn.execute('SELECT count(*) FROM human_work_events').fetchone()[0]==6000
checks.append('6000synthetic records retained, runtime cursor forbids writes; no provider access/workers/customer data')
print('HUMAN_WORK_RESULT='+json.dumps(dict(purpose='human-work-read-repair',
    deployed_failures=failures,baseline_note='Import-only diagnostic working baseline; deployed source fails beforeDB',
    baseline_samples_ms=samples['baseline'],candidate_samples_ms=samples['candidate'],cold_samples_ms=cold,
    cpu_samples_ms=cpu,improvement_ms=before-after,improvement_percent=(before-after)/before*100,costs=costs,pool_stats=pool_stats,
    browser_samples_ms=browser_samples,browser_interaction_samples_ms=interactions,screenshots=screenshots,checks=checks,
    workload='6000 synthetic events;25 visible rows plus next-page sentinel',behaviour_preserved=True)))
