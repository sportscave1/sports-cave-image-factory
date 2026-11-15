"""Real isolated controller input and local fallback, never 18762."""
import sys,time,json,base64,statistics,math
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path[:0]=[str(root/'scripts/studio'),str(root)]
import studio,preview_runtime,draft_ui
from playwright.sync_api import sync_playwright,expect
home=root.parent;owner='codex/v9-p2-01a13216';task='v9-p2';phase=sys.argv[1]
image=preview_runtime.IMAGE_TAG
if phase=='before':preview_runtime.IMAGE_TAG='sha256:5a22bde08670c241dd349f56e374ee5510a58f9f13d077831d1cd9de8746d061'
runtime=preview_runtime.Preview(home,task,owner);samples=[];report={'phase':phase,'scope':'Same current host; exact baseline vs candidate controller image; repeated Tab/text input raster roundtrip, no source writes'}
try:
    frame=runtime.start();(root/'docs/p2-input-signin.jpg').write_bytes(base64.b64decode(frame['image']))
    for _ in range(5):
        start=time.perf_counter()
        events=[{'action':'key','key':'Tab'},{'action':'text','text':'p2'},{'action':'key','key':'Backspace'}]
        if phase=='before':
            for event in events:frame=runtime.event(event)
        else:frame=runtime.event({'action':'input-batch','page':'__signin__','events':events})
        samples.append((time.perf_counter()-start)*1000)
    report['samples_ms']=samples;report['median_ms']=statistics.median(samples);report['p95_ms']=sorted(samples)[math.ceil(.95*len(samples))-1]
    if phase!='before':
        saved_container=runtime.container_id
        for key in ('dashboard','orders','dashboard'):
            navigated=runtime.event({'action':'navigate','page':key});assert navigated['page_key']==key,navigated['page_key']
            runtime.event({'action':'input-batch','page':key,'events':[{'action':'scroll','delta':100},{'action':'scroll','delta':-100}]})
            assert runtime.container_id==saved_container
            for mode in ('tablet','mobile','desktop'):
                sized=runtime.event({'action':'size','mode':mode});assert sized['page_key']==key,(mode,key,sized['page_key'])
        report['actual_os_navigation_and_scroll_batch_passed']=True
        try:runtime.event({'action':'input-batch','page':'orders','events':[{'action':'text','text':'reject'}]})
        except (ValueError,RuntimeError):report['stale_page_rejected']=True
        else:raise AssertionError('Stale batch accepted')
        with studio.locked(home) as file:
            registry=studio.read(file);lease=dict(registry['preview_leases'][task]);registry['preview_leases'][task]['owner']='test-intruder';studio.atomic(file,registry)
        try:
            try:runtime.event({'action':'frame'})
            except RuntimeError:report['real_lease_owner_change_rejected']=True
            else:raise AssertionError('Changed lease accepted')
        finally:
            with studio.locked(home) as file:
                registry=studio.read(file);registry['preview_leases'][task]=lease;studio.atomic(file,registry)
    report['isolation']=runtime.evidence;report['same_container']=bool(runtime.container_id)
finally:
    runtime.stop();preview_runtime.IMAGE_TAG=image
(root/'docs'/('v9-p2-input-'+phase+'.json')).write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='isolation'},indent=2),flush=True)
if phase!='before':
    # The same trusted identity is not needed: this test uses its own authenticated
    # local launcher bootstrap and the existing exact test draft in the new home.
    import threading
    server=draft_ui.DraftServer(home,task,owner,persistent=True);server_thread=threading.Thread(target=server.run,daemon=True);server_thread.start()
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=False);context=browser.new_context(viewport={'width':1600,'height':1000});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(server.origin+'/workspace#token='+server.token)
            expect(page.locator('#ws-image')).to_be_visible(timeout=120000);expect(page.locator('#ws-loading')).to_be_hidden(timeout=120000)
            page.get_by_role('button',name='Files',exact=True).click();page.locator('#ws-list').get_by_role('button',name='orders_page.css',exact=False).click();expect(page.locator('#ed-source')).to_be_enabled()
            field=page.locator('#ed-source');original=field.input_value();field.focus();field.press('Control+End');field.press_sequentially('/* immediate-close recovery */',delay=1);page.once('dialog',lambda d:d.accept());page.close(run_before_unload=True);page=context.new_page();page.goto(server.origin+'/workspace#token='+server.token);expect(page.locator('#ed-source')).to_have_value(original+'/* immediate-close recovery */',timeout=120000);report['immediate_close_recovery_passed']=True
            expect(page.locator('#ws-loading')).to_be_hidden(timeout=120000);page.locator('#ws-undo').click();expect(page.locator('#ed-source')).to_have_value(original)
            page.get_by_role('button',name='Files',exact=True).click();page.locator('#ws-list').get_by_role('button',name='components/sports_cave_top_bar/index.html',exact=False).click();expect(page.locator('#ed-source')).to_be_enabled();field=page.locator('#ed-source');html=field.input_value();assert html.count('<span>Files</span>')==1
            before=(root/'components/sports_cave_top_bar/index.html').read_bytes();field.evaluate('(n,value)=>{n.value=value;n.dispatchEvent(new InputEvent(\"input\",{bubbles:true,inputType:\"insertFromPaste\"}));}',html.replace('<span>Files</span>','<span>Files P2</span>'));page.locator('#ws-save').click();expect(page.locator('#ed-status')).to_contain_text('Saved to the actual draft',timeout=30000);expect(page.locator('#ws-loading')).to_be_hidden(timeout=30000);assert 'Files P2' in server.preview_runtime.last_frame['text'];report['actual_html_saved_and_rendered']=True
            page.locator('#ws-undo').click();expect(page.locator('#ed-status')).to_contain_text('Saved to the actual draft',timeout=30000);expect(page.locator('#ws-loading')).to_be_hidden(timeout=30000);assert (root/'components/sports_cave_top_bar/index.html').read_bytes()==before;assert 'Files P2' not in server.preview_runtime.last_frame['text'];report['html_undo_restored_exact_source_and_preview']=True
            assert not errors,errors
            report['local_fallback_passed']=True;report['local_fallback_errors']=errors;browser.close()
    finally:
        server.stopping=True
        server_thread.join(20);assert not server_thread.is_alive()
    (root/'docs'/('v9-p2-input-'+phase+'.json')).write_text(json.dumps(report,indent=2));print('Local fallback passed',flush=True)
