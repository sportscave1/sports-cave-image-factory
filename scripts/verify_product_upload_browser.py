"""Browser QA against product_upload_local_preview.py, never a live OS URL."""
import json,time,threading,urllib.request,os
from pathlib import Path
import psutil
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/product-uploads';BASE=os.getenv('PRODUCT_UPLOAD_PREVIEW_URL','http://127.0.0.1:8676')
assert urllib.parse.urlparse(BASE).hostname=='127.0.0.1' and urllib.parse.urlparse(BASE).scheme=='http','Browser QA is loopback-only'


def get(path):
    with urllib.request.urlopen(BASE+path) as response:return json.load(response)


def main():
    import sys
    sys.path.insert(0,str(ROOT))
    from tests.test_product_upload_intake import psd
    small=OUT/'interruption-fixture.psd';small.write_bytes(psd(8*1024*1024+73))
    # Stress transfer framing only; this deliberately is not native PSD evidence.
    large=OUT/'large-transfer-fixture.psd'
    with large.open('wb') as f:
        f.write(psd(128));f.truncate(179695966)
    import shutil
    real=OUT/'sportscave-new-designs-template-local.psd'
    shutil.copyfile(Path.home()/'Sportscave Dropbox/Sportscave Team Folder/03_ASSETS/sportscave-new-designs-template.psd',real)
    results={'boundaries':'Real component + intake HTTP + SQL + mapping/queue; Shopify/Dropbox/Photoshop simulated locally.'}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1280,'height':850},permissions=['clipboard-read','clipboard-write'])
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        assert context.request.post(BASE+'/__test/reset').ok
        page.goto(BASE+'/product-uploads');expect(page.locator('#manual')).to_be_enabled()
        expect(page.locator('#return')).to_be_hidden();expect(page.locator('#prompt')).to_be_hidden()
        page.locator('#manual').click();expect(page.locator('#drop')).to_be_hidden()
        for mode in ('DRAFT','LIVE','UPDATE'):
            page.locator('#mode').select_option(mode);page.locator('#copy').click()
            expect(page.locator('#copy')).to_have_text('Copied');expect(page.locator('#return')).to_be_hidden()
            text=page.evaluate('navigator.clipboard.readText()');assert '[ENTER PRODUCT NAME ABOVE]' not in text
            assert 'SELECTED ACTION:' in text
        page.locator('#manual').click();page.locator('#mode').select_option('DRAFT')
        def interrupt(route):
            if 'offset=0' not in route.request.url:route.abort()
            else:route.continue_()
        page.route('**/api/product-uploads/chunk?*',interrupt)
        page.locator('#file').set_input_files(str(small));expect(page.locator('#error')).to_be_visible(timeout=30000)
        assert get('/api/product-uploads/state')['upload']['offset']==4*1024*1024
        page.unroute('**/api/product-uploads/chunk?*',interrupt);page.reload()
        expect(page.locator('#filename')).to_have_text(small.name)
        page.locator('#file').set_input_files(str(small));expect(page.locator('#stage')).to_have_text('Uploaded',timeout=30000)
        expect(page.locator('#return')).to_be_hidden()
        # Failed Clipboard API must not unlock the return step. execCommand is
        # exercised by a real user click in Chromium, not faked as successful.
        page.evaluate("() => {window.originalClipboard=navigator.clipboard.writeText.bind(navigator.clipboard);navigator.clipboard.writeText=async()=>{throw Error('denied')};}")
        page.locator('#copy').click();expect(page.locator('#fallback')).to_be_visible();expect(page.locator('#return')).to_be_hidden()
        page.locator('#fallback-copy').click();expect(page.locator('#return')).to_be_visible()
        page.reload();expect(page.locator('#return')).to_be_visible()
        page.locator('#mode').select_option('LIVE');expect(page.locator('#return')).to_be_hidden()
        page.locator('#copy').click();expect(page.locator('#return')).to_be_visible()
        page.locator('#find').click();page.wait_for_url('**/?page=files&files_path=*')
        assert 'product-images' in page.url
        page.go_back();expect(page.locator('#return')).to_be_visible();expect(page.locator('#mode')).to_have_value('LIVE')
        page.locator('#new').click();page.locator('#mode').select_option('DRAFT')
        # 171 MiB transfer fixture, streamed to a local disk provider. Sample
        # RSS independently of the browser event loop while the upload runs.
        cdp=browser.new_browser_cdp_session()
        pids=[r['id'] for r in cdp.send('SystemInfo.getProcessInfo')['processInfo']]
        def browser_rss():
            return sum(psutil.Process(pid).memory_info().rss for pid in pids if psutil.pid_exists(pid))
        baseline=get('/__test/metrics')['server_rss'];bbase=browser_rss();samples=[];stop=threading.Event()
        def sample():
            while not stop.wait(.15):
                try:samples.append((get('/__test/metrics')['server_rss'],browser_rss()))
                except Exception:pass
        thread=threading.Thread(target=sample,daemon=True);thread.start();started=time.perf_counter()
        try:
            page.locator('#file').set_input_files(str(large));expect(page.locator('#stage')).to_have_text('Uploaded',timeout=60000)
            duration=time.perf_counter()-started
        finally:stop.set();thread.join()
        results['large_upload']={'bytes':large.stat().st_size,'seconds_including_browser_hash':round(duration,3),
            'server_rss_baseline_bytes':baseline,'server_rss_peak_bytes':max(s[0] for s in samples),
            'browser_processes_rss_baseline_bytes':bbase,'browser_processes_rss_peak_bytes':max(s[1] for s in samples),
            'rss_samples':len(samples),'chunk_limit_bytes':4*1024*1024}
        page.locator('#new').click();started=time.perf_counter()
        page.locator('#file').set_input_files(str(real));expect(page.locator('#stage')).to_have_text('Uploaded',timeout=60000)
        results['real_template_upload']={'bytes':real.stat().st_size,'seconds_including_browser_hash':round(time.perf_counter()-started,3),'native_reopen':False}
        page.locator('#copy').click();expect(page.locator('#return')).to_be_visible()
        page.locator('#product').fill('Not yet synced');page.locator('#upload').click()
        expect(page.locator('#detail')).to_contain_text('not found');page.reload()
        expect(page.locator('#product')).to_have_value('Not yet synced')
        page.locator('#product').fill('New Art');page.locator('#upload').dblclick()
        expect(page.locator('#stage')).to_have_text('Waiting for Companion',timeout=10000)
        status=[]
        page.on('response',lambda r:status.append((time.monotonic(),len(r.body()))) if '/api/product-uploads/state' in r.url else None)
        time0=time.monotonic();page.wait_for_timeout(11500)
        results['waiting_poll']={'seconds':round(time.monotonic()-time0,2),'requests':len(status),'response_bytes':[n for _,n in status]}
        page.screenshot(path=str(OUT/'compact-waiting-desktop.png'),full_page=True)
        response=context.request.post(BASE+'/__test/complete');assert response.ok,response.text()
        expect(page.locator('#stage')).to_have_text('Cloud Ready',timeout=15000)
        expect(page.locator('#preview img')).to_be_visible(timeout=15000)
        page.screenshot(path=str(OUT/'compact-completed-desktop.png'),full_page=True)
        count=len(status);page.wait_for_timeout(11000);assert len(status)==count,'Terminal status still polled'
        metrics=get('/__test/metrics');results['preview_asset_fetches']=metrics['preview_asset_fetches']
        source=get('/api/product-uploads/state')['upload'];preview=context.request.get(BASE+source['preview_url'])
        results['preview_bytes']=len(preview.body());assert preview.ok
        fetch_count=len(metrics['preview_asset_fetches']);page.reload();expect(page.locator('#preview img')).to_be_visible(timeout=15000)
        assert len(get('/__test/metrics')['preview_asset_fetches'])==fetch_count,'Refresh rebuilt the cached preview'
        page.locator('#manual').click();expect(page.locator('#mode')).to_be_enabled()
        page.locator('#mode').select_option('UPDATE');expect(page.locator('#copy')).to_be_enabled()
        page.locator('#manual').click();expect(page.locator('#mode')).to_have_value('DRAFT')
        # Browser zoom simulation and Windows 150% device scale; this cannot
        # change the user's Windows display setting and is labelled accordingly.
        narrow=browser.new_context(viewport={'width':390,'height':844},device_scale_factor=1.5,permissions=['clipboard-write'])
        np=narrow.new_page();np.goto(BASE+'/product-uploads');expect(np.locator('#stage')).to_have_text('Cloud Ready')
        np.evaluate('document.body.style.zoom="1.25"');np.screenshot(path=str(OUT/'compact-completed-narrow-125.png'),full_page=True)
        for check in (page,np):
            assert check.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Horizontal overflow'
            bounds=check.locator('#return label,#product,#upload').evaluate_all('(els)=>els.map(e=>{const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,right:r.right}})')
            assert bounds[0]['bottom']<=bounds[1]['top'] and bounds[1]['bottom']<bounds[2]['top']
        # Execute the actual app.py iframe bridge after the child has loaded:
        # the handshake must recover an earlier/missed first height message.
        import ast,re
        tree=ast.parse((ROOT/'app.py').read_text(encoding='utf-8'))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='render_product_uploads_page')
        literals=[n.value for n in ast.walk(function) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
        markup=next(s for s in literals if '<iframe title=' in s)
        bridge=next(s for s in literals if '_scProductUploadsListener' in s)
        shell=context.new_page();shell.goto(BASE+'/');shell.set_content(markup)
        expect(shell.frame_locator('#product-uploads-frame').locator('#stage')).to_have_text('Cloud Ready')
        shell.add_script_tag(content=re.search(r'<script>(.*)</script>',bridge,re.S).group(1))
        shell.wait_for_function("parseInt(document.querySelector('#product-uploads-frame').style.height)<760")
        results['iframe_height_px']=shell.locator('#product-uploads-frame').evaluate('(frame)=>parseInt(frame.style.height)')
        assert 400<=results['iframe_height_px']<760
        shell.close()
        results['browser_checks']=['three manual modes','clipboard real success','clipboard denied + working fallback','4 MiB interruption/resume','mode invalidation','refresh recovery','Files navigation + back','not-found recovery','duplicate click','Companion offline','synthetic verified package completion','cached preview refresh','terminal polling stopped','390px DPR1.5 and CSS zoom125% without overflow','actual app iframe bridge and late-load height handshake']
        results['browser_errors']=errors;assert not errors,errors
        (OUT/'browser-metrics.json').write_text(json.dumps(results,indent=2))
        print(json.dumps(results,indent=2));browser.close()


if __name__=='__main__':main()
