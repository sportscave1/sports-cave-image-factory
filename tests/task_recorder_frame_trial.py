"""Real isolated OS/relay/Windows browser test for passive frame correction."""
import asyncio
import hashlib
import json
from pathlib import Path
import threading
import time
import uuid
from playwright.async_api import async_playwright
from task_recorder.server import Bridge
from task_recorder.attention import FRAME_NAVIGATION

SITE="http://127.0.0.1:18964"
ROOT=Path.home()/"AppData/Local/SportsCaveOS/TaskRecorderFrameFix-64cdf0b0"
bridge=Bridge(ROOT/"acceptance",18934,preview=True)
thread=threading.Thread(target=bridge.serve_forever,daemon=True);thread.start()
def submit(coro):return asyncio.run_coroutine_threadsafe(coro,bridge.loop)
async def engine(fn):return await asyncio.wrap_future(submit(fn()))
async def mode(*wanted):
    end=time.monotonic()+30
    while bridge.runner.mode not in wanted and time.monotonic()<end:await asyncio.sleep(.05)
    assert bridge.runner.mode in wanted,bridge.runner.message
async def sign_in(p):
    user=p.get_by_placeholder("Username or email",exact=True);heading=p.get_by_role("heading",name="Task Recorder",exact=True)
    await user.or_(heading).first.wait_for(timeout=30000)
    if await user.count():
        await user.fill("recorder-preview@example.invalid")
        await p.get_by_placeholder("Password",exact=True).fill("RecorderPreview-Only-2026")
        await p.get_by_role("button",name="Sign in",exact=True).click()
    await heading.wait_for(timeout=30000)
async def main():
    # Manual sign-in equivalent uses synthetic fixture credentials, recording OFF.
    async def login_helper():
        await bridge.runner.open_browser(SITE+"/?page=task_recorder");await sign_in(bridge.runner.page)
    await engine(login_helper)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        p=await browser.new_page(viewport={"width":1280,"height":850});await p.goto(SITE+"/?page=task_recorder");await sign_in(p)
        panel=p.frame_locator('iframe[src="/task-recorder/panel"]')
        if not bridge.agent.credentials():
            await panel.locator('#pair').click();await panel.locator('#code').filter(has_text=__import__('re').compile('[A-Z2-9]{4}-')).wait_for()
            code=await panel.locator('#code').inner_text();local=await browser.new_page()
            from urllib.parse import urlencode
            await local.goto('http://127.0.0.1:18934/pair#'+urlencode({'origin':SITE,'code':code}))
            await local.get_by_label('PC name',exact=True).fill('A Frame correction PC')
            await local.get_by_role('button',name='Continue',exact=True).click()
            await local.get_by_role('button',name='Approve connection on this PC',exact=True).click()
            await local.locator('#message').filter(has_text='PC connected').wait_for();await local.close()
        await panel.locator('#pc').filter(has_text='Connected').wait_for(timeout=35000)
        if await panel.locator('#stop').is_visible():await panel.locator('#stop').click();await mode('stopped')
        await panel.locator('#name').fill('Passive OS navigation regression')
        await panel.locator('#website').fill(SITE+'/');await panel.locator('#record').click();await mode('recording')
        async def dashboard():
            await bridge.runner.page.wait_for_url('**/?page=dashboard',timeout=30000)
            await bridge.runner.page.get_by_text('Active & Upcoming Events',exact=True).wait_for(timeout=30000)
        await engine(dashboard)
        await panel.locator('#stop').click();await mode('stopped')
        assert not any(s['action']=='unsupported' for s in bridge.runner.draft['steps']),bridge.runner.draft
        print('PASS actual OS navigation creates srcdoc frames without false unsupported flags',flush=True)
        original={'version':1,'name':'Original frame issue fixture','inputs':[],'steps':[{'action':'navigate','value':SITE+'/'},{'action':'navigate','value':SITE+'/?page=dashboard'},{'action':'unsupported','reason':FRAME_NAVIGATION}]}
        original['id']=str(uuid.uuid4());original['name']='Original frame issue fixture'
        for step in original['steps']:
            if step.get('action')=='navigate':step['value']=step['value'].replace('https://sports-cave-image-factory.onrender.com',SITE)
        original=bridge.runner.store.save(original);oid=original['id'];bridge.runner.store.metadata(oid,duration_ms=21503)
        path=bridge.runner.store.tasks/(oid+'.json');before=path.read_bytes()
        row=panel.locator(f'tr[data-task-id="{oid}"]')
        await row.get_by_role('button',name='Review step 3 of Original frame issue fixture',exact=True).click()
        await panel.locator('#attentionHeading').filter(has_text='Step 3').wait_for()
        assert FRAME_NAVIGATION in await panel.locator('#recordedReason').inner_text()
        await panel.locator('#correctionValue').fill('Active & Upcoming Events')
        await panel.locator('#repairCopy').click()
        await panel.locator('#notice').filter(has_text='Corrected copy saved').wait_for(timeout=25000)
        corrected=bridge.runner.draft;cid=corrected['id'];assert cid!=oid and path.read_bytes()==before
        assert corrected['steps'][:2]==original['steps'][:2] and corrected['steps'][2]['action']=='wait'
        assert not bridge.runner.page  # Stop closed the recorder; Play must recreate it.
        cr=panel.locator(f'tr[data-task-id="{cid}"]')
        await cr.get_by_role('button',name='Play '+corrected['name'],exact=True).click();await mode('running','completed');await mode('completed')
        async def destination():
            pp=bridge.runner.page
            return {'url':pp.url,'visible':await pp.get_by_text('Active & Upcoming Events',exact=True).is_visible()}
        reached=await engine(destination);assert reached=={'url':SITE+'/?page=dashboard','visible':True},reached
        await panel.locator('#message').filter(has_text='Completed').wait_for(timeout=25000)
        await p.screenshot(path=str(ROOT/'corrected-preview.png'),full_page=True)
        print('PASS OS Needs attention exact step/reason > corrected copy > Play recreates closed browser and reaches dashboard content',flush=True)
        # Genuine embedded input and sign-in remain protected.
        async def frame_input():
            r=bridge.runner;await r.open_browser('http://127.0.0.1:18934/demo');r.draft={**r.blank(),'id':str(uuid.uuid4()),'name':'Frame interaction safety'}
            await r.set_recording(True)
            await r.page.evaluate("document.body.insertAdjacentHTML('beforeend',`<iframe title=FrameTest srcdoc='<button>Frame button</button>'></iframe>`)")
            await r.page.frame_locator('iframe[title=FrameTest]').get_by_role('button',name='Frame button').click()
            end=time.monotonic()+5
            while not any(s['action']=='unsupported' for s in r.draft['steps']) and time.monotonic()<end:await asyncio.sleep(.05)
            assert any('action inside an embedded page' in s.get('reason','') for s in r.draft['steps'])
            await r.set_recording(False)
            r.draft={**r.blank(),'id':str(uuid.uuid4()),'name':'Frame sign-in safety'}
            await r.set_recording(True)
            await r.page.evaluate("document.body.insertAdjacentHTML('beforeend',`<iframe title=PrivacyTest srcdoc='<input type=password>'></iframe>`)")
            end=time.monotonic()+5
            while r.recording and time.monotonic()<end:await asyncio.sleep(.05)
            assert r.mode=='recording_paused' and r.privacy_pause
            await r.stop()
        await engine(frame_input)
        print('PASS real iframe action flagged; dynamic iframe password pauses recording; privacy protections retained',flush=True)
        (ROOT/'focused-evidence.json').write_text(json.dumps({'original_preserved':path.read_bytes()==before,'corrected_task_id':cid,'closed_browser_recreated':True,'destination':reached,'passive_frames_not_actions':True,'actual_frame_input_blocked':True,'frame_signin_privacy':True},indent=2),encoding='utf-8')
        await browser.close()
if __name__=='__main__':
    try:asyncio.run(main())
    finally:bridge.shutdown();bridge.close();thread.join()
