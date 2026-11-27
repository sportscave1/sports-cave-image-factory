"""Container-only populated twelve-week report profiling and output parity."""
import cProfile
import copy
from datetime import date, datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import pstats
import statistics
import sys
import time
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor
import hashlib
import random
import subprocess
from unittest.mock import patch

if not Path('/opt/studio/entry.py').is_file() or {p.name for p in Path('/sys/class/net').iterdir()} != {'lo'}:
    raise RuntimeError('Requires reviewed network-isolated preview')
sys.path.insert(0, '/tmp/source')
for name, source in MODULES.items():
    Path('/tmp/source', name).write_text(source)
os.environ['DATABASE_URL'] = 'postgresql://studio@127.0.0.1:55432/studio?sslmode=disable'
import sports_cave_dashboard as candidate
import baseline_dashboard as baseline

os.environ['SPORTS_CAVE_ADMIN_EMAIL'] = 'preview@example.invalid'
USER = dict(id='report-owner', email='preview@example.invalid', role='admin', is_active=True,
            account_status='active', page_permissions=['reporting'])
START = date(2026, 8, 3)
TODAY = date(2026, 11, 26)
SHEETS = []
TIMERS = []
for day in range(84):
    tasks = [dict(task=f'Synthetic work {day}-{i}', time_blocked='30 min',
                  status=('done', 'couldnt_finish', 'skipped', '')[(day+i)%4],
                  outcome_history=[dict(status='open', version=j) for j in range(4)],
                  actual_elapsed_seconds=1200+i, why='Retain behaviour and access') for i in range(15)]
    sheet = dict(id=str(UUID(int=day+1)), user_id=USER['id'], user_name='Synthetic Owner',
                 sheet_date=(START+timedelta(days=day)).isoformat(), top_tasks=tasks[:3],
                 additional_items=tasks[3:], ratings={'Overall Score': 4},
                 review_data={'worked_well': 'Synthetic progress', 'could_not_finish': 'Synthetic blocker'},
                 planning_data={'carried_forward': []}, daily_summary='Synthetic summary')
    SHEETS.append(sheet)
    for i in range(15):
        TIMERS.append(dict(sheet_id=sheet['id'], task_type='top' if i<3 else 'additional',
                           task_index=i if i<3 else i-3, actual_elapsed_seconds=1200+i,
                           status='completed', outcome_at='2026-10-01T00:00:00+00:00'))

class Backend:
    def list_daily_planner_cycle_archive(self, user_id, anchor):
        assert user_id == USER['id']
        return dict(cycle=dict(id='synthetic-cycle', start_date=START, name='Synthetic twelve-week cycle'),
                    plans=[dict(id=f'plan-{i}', week_number=i, theme=f'Week {i} theme',
                                objectives=[dict(title='Measured progress', tactics=[dict(action='Verify', status='completed')])]) for i in range(1,13)],
                    monthly_reviews=[], query_count=1)

    def list_daily_execution_sheets_for_reporting(self, user_id, start, end, *, limit):
        assert (user_id, start, end, limit) == (USER['id'], START.isoformat(), (START+timedelta(days=83)).isoformat(), 5000)
        return copy.deepcopy(SHEETS)

    def list_daily_execution_timers_for_sheets(self, user_id, ids):
        assert user_id == USER['id'] and len(ids)==84
        return copy.deepcopy(TIMERS)

def run(module):
    with patch.object(module, 'get_supabase_backend', return_value=Backend()):
        return module.load_twelve_week_progress(USER, TODAY)

# Keep the original CPU-only profile to identify the cause; final measurements
# below replace the copying adapter with actual production read functions.
assert run(baseline) == run(candidate)
profile=cProfile.Profile()
profile.runcall(run,baseline)
stream=io.StringIO()
pstats.Stats(profile,stream=stream).sort_stats('cumtime').print_stats(22)
print(stream.getvalue())

from reporting_speed_fixture import backend, DSN, METER
import psycopg
from psycopg.types.json import Jsonb
with psycopg.connect(DSN) as conn:
    conn.execute('CREATE TABLE daily_execution_sheets(id UUID PRIMARY KEY,user_id TEXT,user_name TEXT,sheet_date DATE,top_tasks JSONB,additional_items JSONB,ratings JSONB,review_data JSONB,planning_data JSONB,daily_summary TEXT,updated_at TIMESTAMPTZ DEFAULT now())')
    conn.execute('CREATE TABLE daily_execution_task_timers(id UUID PRIMARY KEY,user_id TEXT,sheet_id UUID,task_type TEXT,task_index INT,actual_elapsed_seconds INT,status TEXT,outcome_at TIMESTAMPTZ,updated_at TIMESTAMPTZ DEFAULT now())')
    conn.execute('CREATE TABLE daily_planner_cycles(id UUID PRIMARY KEY,user_id TEXT,start_date DATE,name TEXT)')
    conn.execute('CREATE TABLE daily_planner_weekly_plans(id UUID PRIMARY KEY,user_id TEXT,cycle_id UUID,week_number INT,theme TEXT)')
    conn.execute('CREATE TABLE daily_planner_weekly_objectives(id UUID PRIMARY KEY,plan_id UUID,position INT,title TEXT,deleted_at TIMESTAMPTZ)')
    conn.execute('CREATE TABLE daily_planner_weekly_tactics(id UUID PRIMARY KEY,plan_id UUID,objective_id UUID,position INT,action TEXT,status TEXT,deleted_at TIMESTAMPTZ)')
    conn.execute('CREATE TABLE daily_planner_monthly_reviews(id UUID PRIMARY KEY,user_id TEXT,cycle_id UUID,month_start DATE,summary JSONB,submitted_at TIMESTAMPTZ)')
    conn.execute('INSERT INTO daily_planner_cycles VALUES (%s,%s,%s,%s)',(UUID(int=9000),USER['id'],START,'Synthetic twelve-week cycle'))
    for i in range(1,13):
        conn.execute('INSERT INTO daily_planner_weekly_plans VALUES (%s,%s,%s,%s,%s)',(UUID(int=9100+i),USER['id'],UUID(int=9000),i,f'Week {i} theme'))
        conn.execute('INSERT INTO daily_planner_weekly_objectives VALUES (%s,%s,1,%s,NULL)',(UUID(int=9200+i),UUID(int=9100+i),'Measured progress'))
        conn.execute('INSERT INTO daily_planner_weekly_tactics VALUES (%s,%s,%s,1,%s,%s,NULL)',(UUID(int=9300+i),UUID(int=9100+i),UUID(int=9200+i),'Verify','completed'))
    for sheet in SHEETS:
        keys=('id','user_id','user_name','sheet_date','top_tasks','additional_items','ratings','review_data','planning_data','daily_summary')
        conn.execute('INSERT INTO daily_execution_sheets('+','.join(keys)+') VALUES('+','.join(['%s']*len(keys))+')',
                     [Jsonb(sheet[k]) if isinstance(sheet[k],(list,dict)) else sheet[k] for k in keys])
    for i,timer in enumerate(TIMERS):
        conn.execute('INSERT INTO daily_execution_task_timers(id,user_id,sheet_id,task_type,task_index,actual_elapsed_seconds,status,outcome_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                     (UUID(int=10000+i),USER['id'],timer['sheet_id'],timer['task_type'],timer['task_index'],timer['actual_elapsed_seconds'],timer['status'],timer['outcome_at']))
    conn.execute("INSERT INTO daily_execution_sheets(id,user_id,sheet_date,top_tasks) VALUES(%s,'other-owner',%s,%s)",
                 (UUID(int=9999),START,Jsonb([dict(task='Other owner hidden')])) )

def run(module):
    with patch.object(module, 'get_supabase_backend', side_effect=backend):
        return module.load_twelve_week_progress(USER, TODAY)

reference=run(baseline)
assert reference == run(candidate)
samples={}; counts={}
costs={}; cpu={}
for label,module in [('baseline',baseline),('candidate',candidate)]:
    samples[label]=[]
    cpu[label]=[]
    METER.update(queries=0,sql_ms=0.)
    count=[0]
    original=module._normalise_daily_sheet
    def measured(sheet):
        count[0]+=1
        return original(sheet)
    with patch.object(module,'_normalise_daily_sheet',measured):
        for _ in range(5):
            start=time.perf_counter()
            process=time.process_time()
            value=run(module)
            samples[label].append((time.perf_counter()-start)*1000)
            cpu[label].append((time.process_time()-process)*1000)
            assert len(value['weeks'])==12 and sum(len(w['days']) for w in value['weeks'])==84
    counts[label]=count[0]//5
    costs[label]=dict(METER)
b,a=map(statistics.median,[samples['baseline'],samples['candidate']])
assert a < b*.75, 'Full-report gain below 25 percent budget'
assert counts == dict(baseline=756,candidate=84)
assert costs['baseline']['queries']==costs['candidate']['queries']==50

# Differential contracts include raw legacy forms: normalization must not be
# assumed idempotent unless the supported inputs actually preserve their output.
rng=random.Random(26)
checks=[]
class FixedDatetime(datetime):
    @classmethod
    def now(cls,tz=None):
        fixed=datetime(2026,11,26,1,tzinfo=timezone.utc)
        return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

for trial in range(40):
    rows=copy.deepcopy(SHEETS[:7])
    rng.shuffle(rows)
    for i,row in enumerate(rows):
        for task in row['top_tasks']+row['additional_items']:
            task.update(status=rng.choice(['','done','skipped','couldnt_finish','unknown']),
                        completed=rng.choice([True,False]),
                        carried_from=START.isoformat() if i and rng.random()<.15 else '',
                        actual_elapsed_seconds=None if trial%2 else 123)
            if trial%3==0:
                task['title']=task.pop('task')
        if i==0:
            row['sheet_date']=rng.choice(['bad-date','2027-01-01',START.isoformat()])
        row['planning_data']['carried_forward']=['Legacy repeated',dict(task='Legacy repeated')]
    timers=copy.deepcopy(TIMERS[:105])
    for timer in timers:
        timer.update(actual_elapsed_seconds=None,status=rng.choice(['running','paused','expired','idle']),
                     deadline_at='2026-11-26T01:10:00+00:00',allocated_seconds=1800,remaining_seconds=600)
    saved=copy.deepcopy((rows,timers))
    with patch.object(baseline,'datetime',FixedDatetime),patch.object(candidate,'datetime',FixedDatetime):
        for method in ['daily_execution_weekly_task_instances','daily_execution_weekly_summary']:
            assert getattr(baseline,method)(rows,timers,today=TODAY)==getattr(candidate,method)(rows,timers,today=TODAY),(trial,method)
    assert (rows,timers)==saved
checks.append('40 seeded raw/legacy/blank/future/carry/outcome/paused-running-expired-timer comparisons; inputs unchanged')

for module in [baseline,candidate]:
    for user in [dict(USER,is_active=False),dict(USER,page_permissions=[]),dict(USER,email='other@example.invalid'),{}]:
        with patch.object(module,'get_supabase_backend',side_effect=AssertionError('Access reached DB')):
            try:module.load_twelve_week_progress(user,TODAY)
            except module.DashboardStorageError:pass
            else:raise AssertionError('Reporting permission bypass')
    with patch.object(module,'get_supabase_backend',side_effect=TimeoutError('Synthetic read timed out')):
        try:module.load_twelve_week_progress(USER,TODAY)
        except module.DashboardStorageError:pass
        else:raise AssertionError('Read failure hidden')
    assert run(module)==reference
    assert backend().get_daily_execution_archive_detail(USER['id'],str(UUID(int=9999)))=={}
checks.append('Actual owner permission gates, other-owner detail denial, timeout surfaced and next read recovers')

# Patch backend once for all threads; each invocation uses independent private
# connections and per-call normalization, with no shared result or stale cache.
with patch.object(candidate,'get_supabase_backend',side_effect=backend):
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(value==reference for value in pool.map(lambda _:candidate.load_twelve_week_progress(USER,TODAY),range(3)))
    for _ in range(8):assert candidate.load_twelve_week_progress(USER,TODAY)==reference
checks.append('Three concurrent full reports and eight-call soak retain exact outputs without shared caching or writes')

# Actual reporting renderer, controls and day drawer; only account/backend
# injection is synthetic. Never start sports_cave_server or a worker.
Path('/tmp/source/reporting_speed_app.py').write_text('''
import os,sys
sys.path.insert(0,'/tmp/source')
from reporting_speed_fixture import backend
import streamlit as st
import reporting_page
import importlib
target=importlib.import_module(os.environ['SPEED_REPORT_VARIANT'])
target.get_supabase_backend=backend
reporting_page.sports_cave_dashboard=target
user=dict(id='report-owner',email='preview@example.invalid',role='admin',is_active=True,account_status='active',page_permissions=['reporting'])
st.set_page_config(layout='wide')
reporting_page._render_twelve_week_progress(user)
st.caption('Synthetic report ready')
''')
from playwright.sync_api import sync_playwright, expect
screenshots={}; browser_samples={}; browser_open={}
evidence_dir=Path('/tmp/reporting-evidence');evidence_dir.mkdir()
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,chromium_sandbox=True,
        args=['--disable-background-networking','--disable-component-update','--num-raster-threads=1','--renderer-process-limit=2'])
    try:
        for label,module_name in [('baseline','baseline_dashboard'),('candidate','sports_cave_dashboard')]:
            env=dict(os.environ,SPEED_REPORT_VARIANT=module_name,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
            log=open('/tmp/reporting-streamlit-'+label+'.log','w')
            process=subprocess.Popen([sys.executable,'-B','-m','streamlit','run','/tmp/source/reporting_speed_app.py',
                 '--server.address=127.0.0.1','--server.port=8502','--server.headless=true',
                 '--server.fileWatcherType=none','--browser.gatherUsageStats=false',
                 '--server.disconnectedSessionTTL=5'],env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                import urllib.request
                for attempt in range(100):
                    try:
                        assert urllib.request.urlopen('http://127.0.0.1:8502/_stcore/health',timeout=1).status==200
                        break
                    except Exception:
                        assert process.poll() is None,Path(log.name).read_text()[-2000:]
                        time.sleep(.1)
                context=browser.new_context(viewport=dict(width=1280,height=1000))
                context.route('**/*',lambda route: route.continue_() if route.request.url.startswith('http://127.0.0.1:8502/') else route.abort())
                browser_samples[label]=[];browser_open[label]=[]
                for i in range(3):
                    page=context.new_page()
                    start=time.perf_counter()
                    page.goto('http://127.0.0.1:8502/',wait_until='domcontentloaded')
                    page.get_by_text('Synthetic report ready',exact=True).wait_for(timeout=30000)
                    page.locator('[data-testid="stDataFrame"] canvas').first.wait_for()
                    assert page.get_by_role('button',name='View week',exact=True).is_enabled()
                    browser_samples[label].append((time.perf_counter()-start)*1000)
                    start=time.perf_counter()
                    page.get_by_role('button',name='View week',exact=True).click()
                    page.get_by_role('button',name='Open day details',exact=True).wait_for()
                    page.get_by_role('button',name='Open day details',exact=True).click()
                    page.get_by_text('Win: Synthetic progress | Blocker: Synthetic blocker',exact=True).wait_for()
                    expect(page.locator('[data-testid="stDataFrame"]')).to_have_count(5)
                    browser_open[label].append((time.perf_counter()-start)*1000)
                    assert page.locator('[data-testid="stException"]').count()==0
                    if i==2:
                        for view,width,height in [('desktop',1280,1000),('mobile',390,844)]:
                            page.set_viewport_size(dict(width=width,height=height))
                            page.wait_for_timeout(500)
                            page.evaluate('document.activeElement?.blur()')
                            page.mouse.move(0,0)
                            page.locator('[data-testid="stStatusWidget"]').wait_for(state='hidden')
                            data=page.screenshot(full_page=True,animations='disabled')
                            (evidence_dir/f'{label}-{view}.png').write_bytes(data)
                            screenshots[f'{label}-{view}']=hashlib.sha256(data).hexdigest()
                    page.close()
                # Three same-revision simultaneous tabs, report -> drawer.
                tabs=[context.new_page() for _ in range(3)]
                for page in tabs:page.goto('http://127.0.0.1:8502/',wait_until='domcontentloaded')
                for page in tabs:
                    page.get_by_text('Synthetic report ready',exact=True).wait_for()
                    page.get_by_role('button',name='View week',exact=True).click()
                    page.get_by_role('button',name='Open day details',exact=True).click()
                    page.get_by_text('Win: Synthetic progress | Blocker: Synthetic blocker',exact=True).wait_for()
                    expect(page.locator('[data-testid="stDataFrame"]')).to_have_count(5)
                    assert page.locator('[data-testid="stException"]').count()==0
                context.close()
            finally:
                process.terminate();process.wait(timeout=15);log.close()
    finally:browser.close()
for view in ['desktop','mobile']:
    from PIL import Image,ImageChops
    before_image=Image.open(evidence_dir/f'baseline-{view}.png').convert('RGB')
    after_image=Image.open(evidence_dir/f'candidate-{view}.png').convert('RGB')
    assert before_image.size==after_image.size
    changed=sum(pixel!=(0,0,0) for pixel in ImageChops.difference(before_image,after_image).getdata())
    # Browser canvas borders can rasterize two isolated pixels differently.
    # No masking: permit at most eight pixels in the entire >=329k-pixel frame.
    assert changed<=8,('Visual parity',view,changed)
    screenshots[view+'_changed_pixels']=changed
assert statistics.median(browser_samples['candidate'])<=statistics.median(browser_samples['baseline'])*1.1
assert statistics.median(browser_open['candidate'])<=statistics.median(browser_open['baseline'])*1.1
checks.append('Actual Streamlit/Chromium 3 full report and week/day samples per revision; 3 tabs, unmasked desktop/mobile PNG comparison <=8 pixels')
with psycopg.connect(DSN) as conn:
    assert conn.execute('SELECT count(*) FROM daily_execution_sheets').fetchone()[0]==85
    assert conn.execute('SELECT count(*) FROM daily_execution_task_timers').fetchone()[0]==1260
checks.append('All synthetic records retained; read-only cursor forbids mutations; no providers/workers or production data')
print('REPORTING_RESULT='+json.dumps(dict(purpose='reporting-normalisation',
    baseline_samples_ms=samples['baseline'],candidate_samples_ms=samples['candidate'],
    normalisations=counts,improvement_ms=b-a,improvement_percent=(b-a)/b*100,
    cpu_samples_ms=cpu,costs=costs,
    browser_samples_ms=browser_samples,browser_open_samples_ms=browser_open,screenshots=screenshots,checks=checks,
    workload='84 synthetic sheets,1260 tasks,1260 timers; complete 12-week/84-day report',
    behaviour_preserved=True)))
