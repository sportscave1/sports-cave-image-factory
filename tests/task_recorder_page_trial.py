"""Focused full OS/relay/Windows helper trial using disposable local tasks only."""
import asyncio
import json
from pathlib import Path
import sys
import threading
import time
import uuid
from playwright.async_api import async_playwright
from task_recorder.server import Bridge

SITE="http://127.0.0.1:18962"
ROOT=Path.home()/"AppData/Local/SportsCaveOS/TaskRecorderPage-Acceptance-64cdf0b0"
ROOT.mkdir(parents=True,exist_ok=True)
bridge=Bridge(ROOT,18932,preview=True)
thread=threading.Thread(target=bridge.serve_forever,daemon=True);thread.start()
def submit(coro):return asyncio.run_coroutine_threadsafe(coro,bridge.loop)
async def engine(fn):return await asyncio.wrap_future(submit(fn()))
async def wait_mode(*modes):
    end=time.monotonic()+25
    while bridge.runner.mode not in modes and time.monotonic()<end:await asyncio.sleep(.05)
    assert bridge.runner.mode in modes,bridge.runner.state()
async def main():
    global bridge,thread
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        page=await browser.new_page(viewport={"width":1450,"height":1000})
        page.set_default_timeout(20000)
        await page.goto(SITE+"/?page=task_recorder")
        await page.get_by_placeholder("Username or email",exact=True).fill("recorder-preview@example.invalid")
        await page.get_by_placeholder("Password",exact=True).fill("RecorderPreview-Only-2026")
        await page.get_by_role("button",name="Sign in",exact=True).click()
        panel=page.frame_locator('iframe[src="/task-recorder/panel"]')
        assert await page.get_by_role("dialog").count()==0
        assert await page.get_by_role("button",name="Open recorder",exact=True).count()==0
        if not bridge.agent.credentials():
            await panel.locator("#pair").click()
            await panel.locator("#code").filter(has_text=__import__('re').compile('[A-Z2-9]{4}-')).wait_for()
            code=await panel.locator("#code").inner_text()
            local=await browser.new_page()
            from urllib.parse import urlencode
            await local.goto("http://127.0.0.1:18932/pair#"+urlencode({"origin":SITE,"code":code}))
            await local.get_by_label("PC name",exact=True).fill("A Page upgrade PC")
            await local.get_by_role("button",name="Continue",exact=True).click()
            await local.get_by_role("button",name="Approve connection on this PC",exact=True).click()
            await local.locator("#message").filter(has_text="PC connected").wait_for()
            await local.close()
        await panel.locator("#pc").filter(has_text="Connected").wait_for(timeout=35000)
        if await panel.locator("#stop").is_visible():
            await panel.locator("#stop").click();await wait_mode("stopped")
        await panel.locator("#name").fill("Clicking to Home")
        await panel.locator("#website").fill("http://127.0.0.1:18932/demo/form")
        await panel.locator("#record").click();await wait_mode("recording")
        async def click_home():await bridge.runner.page.get_by_role("link",name="Home",exact=True).click()
        await engine(click_home)
        await panel.locator("#stop").click();await wait_mode("stopped")
        task=bridge.runner.draft;tid=task["id"]
        row=panel.locator(f'tr[data-task-id="{tid}"]')
        await row.get_by_role("button",name="Play Clicking to Home",exact=True).wait_for()
        assert task["name"]=="Clicking to Home" and len(task["steps"])>=2
        meta=bridge.runner.store.metadata(tid);assert meta['duration_ms']>=0
        assert await row.locator('td').nth(1).inner_text()!='—'
        await row.get_by_role("button",name="Play Clicking to Home",exact=True).click();await wait_mode("running","completed");await wait_mode("completed")
        assert bridge.runner.store.get(tid)["name"]=="Clicking to Home"
        await row.get_by_role("button",name="Rename Clicking to Home",exact=True).click()
        await row.get_by_role("textbox",name="New name for Clicking to Home",exact=True).fill("Clicking to Home — verified")
        await row.get_by_role("button",name="Save name for Clicking to Home",exact=True).click()
        await row.get_by_role("button",name="Play Clicking to Home — verified",exact=True).wait_for()
        assert bridge.runner.store.get(tid)["name"]=="Clicking to Home — verified"
        await page.screenshot(path=str(ROOT/"embedded-local.png"),full_page=True)
        await page.reload();await panel.locator("#pc").filter(has_text="Connected").wait_for()
        await row.get_by_role("button",name="Play Clicking to Home — verified",exact=True).wait_for()
        print("PASS embedded full OS Record Clicking to Home > Stop autosave > metadata > one-click Play > inline rename > refresh",flush=True)
        frame=page.frames[-1]
        # The recorder iframe sizes to its contents; vertical scrolling belongs to the OS.
        recorder_frame=next(f for f in page.frames if f.url.endswith('/task-recorder/panel'))
        assert await recorder_frame.locator('body').evaluate('(e)=>e.scrollHeight<=window.innerHeight+3')
        # Separate disposable task, deleted through authenticated OS controls.
        disposable=bridge.runner.store.save({**task,"id":str(uuid.uuid4()),"name":"Disposable deletion trial"})
        did=disposable['id'];dr=panel.locator(f'tr[data-task-id="{did}"]')
        await dr.get_by_role('button',name='Delete Disposable deletion trial',exact=True).click()
        await dr.get_by_role('button',name='Confirm delete Disposable deletion trial',exact=True).click()
        await dr.wait_for(state='detached')
        assert not any(t['id']==did for t in bridge.runner.store.list())
        # Multi-step real local fixture: completed fills, wait gates, more actions.
        multi=bridge.runner.store.save({"version":1,"id":str(uuid.uuid4()),"name":"Pause resume stop trial","inputs":[],"steps":[
            {"action":"navigate","value":"http://127.0.0.1:18932/demo/form"},
            {"action":"fill","locator":{"by":"label","value":"Product name"},"value":"First fill once"},
            {"action":"wait","locator":{"by":"id","value":"trial-gate-one"},"timeout_ms":30000},
            {"action":"fill","locator":{"by":"label","value":"Headline"},"value":"After resume"},
            {"action":"wait","locator":{"by":"id","value":"trial-gate-two"},"timeout_ms":30000},
            {"action":"fill","locator":{"by":"label","value":"Destination URL"},"value":"https://example.com/must-not-run"}]})
        mid=multi['id'];mr=panel.locator(f'tr[data-task-id="{mid}"]')
        await mr.get_by_role('button',name='Play Pause resume stop trial',exact=True).click();await wait_mode('running')
        while bridge.runner.index<2:await asyncio.sleep(.05)
        await panel.locator('#pause').click();await wait_mode('paused')
        await panel.locator('#resume').wait_for(state='visible')
        await page.reload()
        await panel.locator('#resume').wait_for(state='visible')
        assert bridge.runner.mode=='paused' and bridge.runner.run_id==mid
        # Select another task while paused: Stop/Resume remain bound to mid.
        await row.get_by_role('button',name='Select Clicking to Home — verified',exact=True).click()
        await mr.get_by_role('button',name='Delete Pause resume stop trial',exact=True).click()
        await mr.get_by_role('button',name='Confirm delete Pause resume stop trial',exact=True).click()
        await mr.get_by_role('alert').filter(has_text='Stop this task first.').wait_for()
        async def edit_fixture():
            p=bridge.runner.page
            await p.get_by_label('Product name',exact=True).fill('Manual sentinel after first step')
            await p.evaluate("document.body.insertAdjacentHTML('beforeend','<div id=trial-gate-one>ready</div>')")
        await engine(edit_fixture)
        await panel.locator('#resume').click();await wait_mode('running')
        while bridge.runner.index<4:await asyncio.sleep(.05)
        async def read_fields():return await bridge.runner.page.get_by_label('Product name',exact=True).input_value(),await bridge.runner.page.get_by_label('Headline',exact=True).input_value(),await bridge.runner.page.get_by_label('Destination URL',exact=True).input_value()
        fields=await engine(read_fields);assert fields==('Manual sentinel after first step','After resume',''),fields
        await panel.locator('#stop').click();await wait_mode('stopped')
        assert bridge.runner.store.get(mid)['name']=='Pause resume stop trial'
        print('PASS Play > Pause > select another row > active delete protection > Resume without repeated completed fill > Stop',flush=True)
        # Restart this isolated helper, preserving task names and deletion.
        await asyncio.to_thread(bridge.shutdown);await asyncio.to_thread(bridge.close);thread.join()
        bridge=Bridge(ROOT,18932,preview=True);thread=threading.Thread(target=bridge.serve_forever,daemon=True);thread.start()
        await panel.locator('#pc').filter(has_text='Connected').wait_for(timeout=35000)
        assert bridge.runner.store.get(tid)['name']=='Clicking to Home — verified'
        assert not any(t['id']==did for t in bridge.runner.store.list())
        await page.reload();await row.get_by_role('button',name='Play Clicking to Home — verified',exact=True).wait_for()
        assert await dr.count()==0
        # Offline feedback without touching the user's real paired helper.
        await asyncio.to_thread(bridge.shutdown);await asyncio.to_thread(bridge.close);thread.join()
        await panel.locator('#pc').filter(has_text='Offline').wait_for(timeout=75000)
        assert await row.get_by_role('button',name='Play Clicking to Home — verified',exact=True).is_disabled()
        assert await panel.locator('#setup').is_visible()
        print('PASS helper restart/name persistence, durable deletion after restart/refresh, disconnected feedback',flush=True)
        await page.screenshot(path=str(ROOT/'offline.png'),full_page=True)
        (ROOT/'focused-evidence.json').write_text(json.dumps({'recording_id':tid,'name':'Clicking to Home — verified','recorded_duration_ms':meta['duration_ms'],'steps':len(task['steps']),'deleted_id':did,'pause_resume_stop':True,'completed_steps_not_repeated':True,'active_delete_rejected':True,'restart_persistence':True,'offline_feedback':True},indent=2))
        await browser.close()

if __name__=='__main__':
    try:asyncio.run(main())
    finally:
        if thread.is_alive():bridge.shutdown();bridge.close();thread.join()
