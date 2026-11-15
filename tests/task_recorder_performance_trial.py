"""Focused full OS/auth/relay/helper trial, isolated storage and loopback only.
Start scripts/task_recorder_preview.py --root <isolated-root> --port 18965 first.
"""
import asyncio
import json
from pathlib import Path
import threading
import time
import uuid
from urllib.parse import urlencode
from playwright.async_api import async_playwright
from task_recorder.server import Bridge

SITE="http://127.0.0.1:18965"
ROOT=Path.home()/"AppData/Local/SportsCaveOS/TaskRecorderPerformance-fa5a2404"
bridge=Bridge(ROOT/"helper",18935,preview=True)
thread=threading.Thread(target=bridge.serve_forever,daemon=True);thread.start()
async def engine(fn):return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(fn(),bridge.loop))
async def mode(*wanted):
    deadline=time.monotonic()+35
    while bridge.runner.mode not in wanted and time.monotonic()<deadline:await asyncio.sleep(.04)
    assert bridge.runner.mode in wanted,bridge.runner.message
async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        page=await browser.new_page(viewport={"width":1280,"height":850})
        await page.goto(SITE+"/?page=task_recorder")
        login=page.get_by_placeholder("Username or email",exact=True)
        await login.fill("recorder-preview@example.invalid")
        await page.get_by_placeholder("Password",exact=True).fill("RecorderPreview-Only-2026")
        await page.get_by_role("button",name="Sign in",exact=True).click()
        await page.get_by_role("heading",name="Task Recorder",exact=True).wait_for(timeout=30000)
        panel=page.frame_locator('iframe[src="/task-recorder/panel"]')
        if not bridge.agent.credentials():
            await panel.locator('#pair').click()
            await panel.locator('#code').filter(has_text=__import__('re').compile('[A-Z2-9]{4}-')).wait_for()
            code=await panel.locator('#code').inner_text()
            pc=await browser.new_page()
            await pc.goto('http://127.0.0.1:18935/pair#'+urlencode({'origin':SITE,'code':code}))
            await pc.get_by_label('PC name',exact=True).fill('Performance trial PC')
            await pc.get_by_role('button',name='Continue',exact=True).click()
            await pc.get_by_role('button',name='Approve connection on this PC',exact=True).click()
            await pc.locator('#message').filter(has_text='PC connected').wait_for();await pc.close()
        await panel.locator('#pc').filter(has_text='Connected').wait_for(timeout=35000)
        await panel.locator('#name').fill('Everyday performance trial')
        await panel.locator('#website').fill('http://127.0.0.1:18935/demo')
        await panel.locator('#record').click();await mode('recording')
        async def demonstrate():
            await bridge.runner.page.get_by_role('link',name='Start product form',exact=True).click()
            await bridge.runner.page.get_by_label('Product name',exact=True).fill('Synthetic local trial')
        await engine(demonstrate)
        await panel.locator('#stop').click();await mode('stopped')
        saved=bridge.runner.draft;task_id=saved['id']
        row=panel.locator(f'tr[data-task-id="{task_id}"]')
        await row.get_by_role('button',name='Play '+saved['name'],exact=True).wait_for(timeout=15000)
        assert not bridge.runner.page
        await row.get_by_role('button',name='Play '+saved['name'],exact=True).click()
        await mode('completed')
        async def result():
            return {'url':bridge.runner.page.url,'value':await bridge.runner.page.get_by_label('Product name',exact=True).input_value()}
        reached=await engine(result);assert reached['value']=='Synthetic local trial'
        await panel.locator('#message').filter(has_text='Completed').wait_for(timeout=15000)
        print('PASS full OS Record > autosave > closed-browser Play > confirmed field value, real auth/relay/helper',flush=True)
        # A synthetic wait keeps a multi-step run open so acknowledged controls can
        # be exercised without racing fast clicks or creating external writes.
        async def save_wait():
            task={'version':1,'id':str(uuid.uuid4()),'name':'Synthetic control trial','inputs':[],
                  'steps':[{'action':'navigate','value':'http://127.0.0.1:18935/demo/form'},
                           {'action':'fill','locator':{'by':'label','value':'Product name'},'value':'First step kept'},
                           {'action':'wait','locator':{'by':'text','value':'Trial release marker'},'timeout_ms':30000},
                           {'action':'wait','locator':{'by':'text','value':'Second trial release marker'},'timeout_ms':30000},
                           {'action':'fill','locator':{'by':'label','value':'Headline'},'value':'Must not run after Stop'}]}
            return bridge.runner.store.save(task)
        control=await engine(save_wait);cr=panel.locator(f'tr[data-task-id="{control["id"]}"]')
        await cr.get_by_role('button',name='Play '+control['name'],exact=True).click();await mode('running')
        async def wait_step():
            deadline=time.monotonic()+10
            while bridge.runner.index<2 and time.monotonic()<deadline:await asyncio.sleep(.02)
            assert bridge.runner.index==2
        await engine(wait_step)
        await panel.locator('#pause').click()
        async def release():
            await bridge.runner.page.evaluate("document.body.insertAdjacentHTML('beforeend','<p>Trial release marker</p>')")
        await engine(release);await mode('paused')
        await panel.locator('#resume').wait_for(state='visible',timeout=15000)
        async def change_completed_field():
            await bridge.runner.page.get_by_label('Product name',exact=True).fill('Completed step not repeated')
            # A second missing marker holds the next step after Resume.
        await engine(change_completed_field)
        await panel.locator('#resume').click();await mode('running')
        async def check_position():
            deadline=time.monotonic()+10
            while bridge.runner.index<3 and time.monotonic()<deadline:await asyncio.sleep(.02)
            assert bridge.runner.index==3
            assert await bridge.runner.page.get_by_label('Product name',exact=True).input_value()=='Completed step not repeated'
            assert await bridge.runner.page.get_by_label('Headline',exact=True).input_value()==''
        await engine(check_position)
        await panel.locator('#stop').click();await mode('stopped')
        assert bridge.runner.index==3 and not bridge.runner.page
        assert bridge.runner.store.get(control['id'])['name']==control['name']
        print('PASS acknowledged Pause > Resume from same step > Stop cancels wait and preserves saved task',flush=True)
        # Reopening the page reads the real terminal state, never submits a start.
        await page.reload();await panel.locator('#pc').filter(has_text='Connected').wait_for(timeout=20000)
        assert bridge.runner.mode=='stopped'
        await page.screenshot(path=str(ROOT/'local-performance.png'),full_page=True)
        (ROOT/'trial-evidence.json').write_text(json.dumps({'destination':reached,'record_autosave_play':True,'pause_resume_stop':True,'no_repeated_completed_steps':bridge.runner.index==3,'page_reload_no_restart':True,'isolated_storage':str(ROOT/'helper')},indent=2),encoding='utf-8')
        await browser.close()
if __name__=='__main__':
    try:asyncio.run(main())
    finally:bridge.shutdown();bridge.close();thread.join()
