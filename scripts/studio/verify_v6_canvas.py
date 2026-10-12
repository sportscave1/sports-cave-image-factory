"""Actual isolated draft raster in the V6 UI; disposable headless browser profile."""
import argparse,json,threading,time
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
import draft_ui,studio
from verify_preview_runtime import request,HOME

def main(task,owner,report):
    server=draft_ui.DraftServer(HOME,task,owner,idle_seconds=300)
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    result={'task':task,'scope':'Actual local V6 workspace and real Docker raster; not hosted HTTPS'}
    try:
        frame=request(server,'start-preview')
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            context=browser.new_context(viewport={'width':1440,'height':900})
            context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(('http://127.0.0.1:','data:')) else r.abort())
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            t=time.monotonic();page.goto(server.origin+'/workspace#token='+server.token)
            expect(page.locator('#ws-title')).to_contain_text('V6')
            page.locator('#ws-start').click();expect(page.locator('#ws-image')).to_be_visible()
            expect(page.locator('#ws-status')).to_contain_text('Preview running')
            result['warm_canvas_open_seconds']=round(time.monotonic()-t,3)
            target=next(x for x in frame['inspect_targets'] if x['component']=='title')
            box=page.locator('#ws-image').bounding_box()
            page.locator('#ws-inspect').click()
            page.locator('#ws-image').click(position={'x':target['x']*box['width']/frame['width'],'y':target['y']*box['height']/frame['height']})
            expect(page.locator('#ws-inspection')).to_contain_text('Mapped component: title')
            expect(page.locator('#ws-source-location')).to_contain_text('app.py:')
            expect(page.locator('#ed-text')).to_be_visible()
            page.screenshot(path=str(report.with_suffix('.png')))
            page.get_by_role('button',name='Tablet',exact=True).click();expect(page.locator('[data-size="tablet"]')).to_have_attribute('aria-pressed','true')
            page.get_by_role('button',name='Mobile',exact=True).click();expect(page.locator('[data-size="mobile"]')).to_have_attribute('aria-pressed','true')
            page.set_viewport_size({'width':390,'height':900})
            expect(page.locator('.ws-left')).not_to_be_visible();expect(page.locator('.ws-right')).not_to_be_visible()
            page.screenshot(path=str(report.with_name(report.stem+'-mobile.png')))
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.locator('#ws-stop').click();expect(page.locator('#ws-status')).to_contain_text('Preview stopped')
            assert server.preview_runtime.name is None
            result.update({'actual_raster_and_click_inspection':True,'tablet_mobile_canvas':True,'selected_source_location':True,'stop':True,'browser_errors':errors})
            assert not errors,errors
            browser.close()
    finally:
        server.stopping=True;thread.join(10)
    studio.atomic(report,result);print(json.dumps(result,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task',required=True);p.add_argument('--owner',required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();main(a.task,a.owner,a.report)
