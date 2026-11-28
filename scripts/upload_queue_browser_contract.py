"""Actual gallery card and durable queue in the network-isolated synthetic preview."""
import os,sys,time,json,subprocess,signal,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from PIL import Image,ImageChops

assert {p.name for p in Path('/sys/class/net').iterdir()}=={'lo'}
os.environ['DATABASE_URL']='postgresql://studio@127.0.0.1:55432/studio?sslmode=disable'
# Release idle preview browser/server resources; retain the synthetic PostgreSQL.
me=os.getpid()
for p in Path('/proc').iterdir():
    if p.name.isdigit() and int(p.name)!=me:
        try:
            if any(s in (p/'cmdline').read_bytes() for s in (b'import controller',b'streamlit',b'chrome',b'playwright/driver')):os.kill(int(p.name),signal.SIGTERM)
        except (FileNotFoundError,ProcessLookupError):pass
Path('/tmp/source/upload_browser_app.py').write_text('''
import os,sys
sys.path.insert(0,'/tmp/source')
import streamlit as st
import design_review_page as gallery
from psd_directory import REVIEW_FOLDER
st.set_page_config(layout='wide')
user=dict(id='synthetic-browser',role='admin',is_active=True,account_status='active',page_permissions=['Files'])
source={'.tag':'file','id':'id:synthetic-browser','rev':'synthetic-rev','name':'Synthetic.psd','path_display':REVIEW_FOLDER+'/Synthetic.psd'}
from pathlib import Path
st.html(Path('/tmp/source/components/design_review_gallery.css').read_text())
with st.container(key='design-review-gallery'):
 with st.container(key='design-review-grid'):
  columns=st.columns(2)
  with columns[0]:gallery._card(None,user,source,dict(design_name='Synthetic artwork',sport='Cricket'),'','synthetic-card',None)
st.caption('Synthetic gallery ready')
''')
frames=Path('/tmp/upload-browser-frames');frames.mkdir()
results={}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,chromium_sandbox=True,args=['--disable-background-networking','--disable-component-update','--num-raster-threads=1','--renderer-process-limit=2'])
    try:
        for label,source in [('baseline',BASELINE_QUEUE),('candidate',CANDIDATE_QUEUE)]:
            Path('/tmp/source/product_upload_staff_queue.py').write_text(source)
            log=open('/tmp/upload-'+label+'.log','w')
            server=subprocess.Popen([sys.executable,'-B','-m','streamlit','run','/tmp/source/upload_browser_app.py','--server.address=127.0.0.1','--server.port=8502','--server.headless=true','--server.fileWatcherType=none','--browser.gatherUsageStats=false'],env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'),stdout=log,stderr=subprocess.STDOUT)
            try:
                for attempt in range(100):
                    try:
                        if urllib.request.urlopen('http://127.0.0.1:8502/_stcore/health',timeout=1).status==200:break
                    except Exception:time.sleep(.1)
                context=browser.new_context(viewport=dict(width=1280,height=900))
                import io
                image_buffer=io.BytesIO();Image.new('RGB',(640,480),(30,55,75)).save(image_buffer,format='PNG')
                context.route('**/*',lambda route:route.continue_() if route.request.url.startswith('http://127.0.0.1:8502/') else route.abort())
                context.route('**/api/design-review/thumbnail?*',lambda route:route.fulfill(status=200,content_type='image/png',body=image_buffer.getvalue()))
                samples=[]
                for i in range(3):
                    page=context.new_page();page.goto('http://127.0.0.1:8502/')
                    page.get_by_text('Synthetic gallery ready',exact=True).wait_for(timeout=30000)
                    expect(page.get_by_role('button',name='Add to queue',exact=True)).to_be_enabled()
                    assert page.locator('[data-testid="stException"]').count()==0
                    if i==0:
                        for view,width,height in [('desktop',1280,900),('mobile',390,844)]:
                            page.set_viewport_size(dict(width=width,height=height));page.wait_for_timeout(500)
                            page.locator('[data-testid="stStatusWidget"]').wait_for(state='hidden')
                            page.screenshot(path=str(frames/f'{label}-{view}.png'),full_page=True,animations='disabled')
                        page.set_viewport_size(dict(width=1280,height=900))
                    t=time.perf_counter();page.get_by_role('button',name='Add to queue',exact=True).click()
                    try:page.get_by_text('Added to upload queue',exact=False).wait_for(timeout=30000)
                    except Exception:
                        print(page.locator('body').inner_text(),flush=True);print(Path(log.name).read_text()[-5000:],flush=True);raise
                    samples.append((time.perf_counter()-t)*1000)
                results[label]=samples
                # Three retained tabs request the same revision; PostgreSQL uniqueness remains authoritative.
                import psycopg
                with psycopg.connect(os.environ['DATABASE_URL']) as conn:
                    assert conn.execute("SELECT count(*) FROM product_upload_staff_jobs WHERE source_id='id:synthetic-browser'").fetchone()[0]==1
                    assert conn.execute("SELECT count(*) FROM product_upload_staff_requests WHERE requester='synthetic-browser'").fetchone()[0]==1
                context.close()
            finally:server.terminate();server.wait(timeout=20);log.close()
    finally:browser.close()
for view in ('desktop','mobile'):
    a=Image.open(frames/f'baseline-{view}.png').convert('RGB');b=Image.open(frames/f'candidate-{view}.png').convert('RGB')
    assert a.size==b.size
    assert ImageChops.difference(a,b).getbbox() is None,view+' visual mismatch'
print('UPLOAD_BROWSER_RESULT='+json.dumps(results),flush=True)
