"""Focused capture/runner regressions with disposable browser state only."""
import asyncio
import json
import uuid
import pytest
from task_recorder.runner import Runner
from task_recorder.schema import Invalid, validate_task
from task_recorder.attention import issues
from task_recorder.device import DeviceAgent


def task(steps):
    return dict(version=1,name="Playback regression",inputs=[],steps=steps)


async def until(fn):
    for _ in range(160):
        if fn(): return
        await asyncio.sleep(.025)
    raise AssertionError("Expected runner state did not arrive")


def test_old_product_prerequisite_and_generic_target_do_not_launch(tmp_path):
    async def run():
        r=Runner(tmp_path,headless=True)
        saved=r.store.save(task([
            dict(action="navigate",value="https://example.com/?page=product_uploads"),
            dict(action="wait",locator=dict(by="text",value="Copied"),timeout_ms=30000),
            dict(action="click",locator=dict(by="test_id",value="stBaseButton-primary"))]))
        before=(r.store.tasks/(saved["id"]+".json")).read_bytes()
        with pytest.raises(Invalid,match="source prerequisite"):
            await r.play(saved["id"],{})
        assert r.context is None
        assert (r.store.tasks/(saved["id"]+".json")).read_bytes()==before
        saved["steps"][0]["value"]+="&upload="+str(uuid.uuid4())
        assert issues(saved)[0]["kind"]=="target"
        saved["steps"][-1]["locator"]=dict(by="role",role="button",value="Generate Mockups")
        assert not issues(saved)
    asyncio.run(run())


def test_capture_unique_names_frames_flush_privacy_and_rerender(tmp_path):
    async def run():
        r=Runner(tmp_path,headless=True)
        try:
            await r.open_browser()
            html="""<button data-testid=stBaseButton-primary>Generate Mockups</button>
              <button data-testid=stBaseButton-primary>Other</button>
              <iframe title="Editor" srcdoc="<label>Note<input></label>"></iframe>"""
            await r.page.route("http://fixture.invalid/**",lambda route:route.fulfill(body=html,content_type="text/html"))
            await r.page.goto("http://fixture.invalid/")
            r.draft=task([dict(action="navigate",value="https://example.com")])
            await r.set_recording(True)
            await r.page.get_by_role("button",name="Generate Mockups",exact=True).click()
            f=r.page.frame_locator('iframe[title="Editor"]')
            await f.get_by_label("Note").fill("pending frame text")
            await r.set_recording(False)
            assert r.draft["steps"][1]["locator"]==dict(by="role",role="button",value="Generate Mockups")
            assert r.draft["steps"][-1]["value"]=="pending frame text"
            assert r.draft["steps"][-1]["locator"]["frames"]==[dict(by="title",value="Editor")]
            assert not issues(r.draft)
            await r.set_recording(True)
            await r.page.evaluate("""() => {document.body.insertAdjacentHTML('beforeend','<button>Duplicate</button><button>Duplicate</button>')}""")
            await r.page.get_by_role("button",name="Duplicate",exact=True).nth(1).click()
            await r.set_recording(False)
            assert r.draft["steps"][-1]["action"]=="unsupported"
            # Passive frames didn't fabricate actions, and a sensitive frame pauses capture.
            r.draft=task([dict(action="navigate",value="https://example.com")])
            await r.set_recording(True)
            await r.page.evaluate("""() => {const p=document.createElement('input');p.type='password';document.body.append(p)}""")
            await until(lambda:r.privacy_pause)
            assert len(r.draft["steps"])==1
        finally: await r.close()
    asyncio.run(run())


def test_missing_ambiguous_pause_stop_duplicate_and_terminal_ownership(tmp_path):
    async def run():
        r=Runner(tmp_path,headless=True)
        agent=DeviceAgent(r,"http://127.0.0.1:18999",preview=True)
        try:
            await r.open_browser()
            await r.page.set_content("<button>Duplicate</button><button>Duplicate</button>")
            saved=r.store.save(task([dict(action="click",locator=dict(by="role",role="button",value="Duplicate"),timeout_ms=500)]))
            await r.play(saved["id"],{},operation_id="ambiguous")
            await until(lambda:r.mode=="paused")
            assert "Step 1 of 1" in r.message and "ambiguous (2 matches)" in r.message
            with pytest.raises(Invalid,match="Stop"): await r.play(saved["id"],{})
            await r.stop()
            assert not r.state()["active_task_id"] and not r.busy()
            await agent.perform("rename",dict(id=saved["id"],name="Stopped editable"),"rename")
            await r.open_browser()
            await r.page.set_content("<p>Waiting</p>")
            saved=r.store.save(task([dict(action="click",locator=dict(by="role",role="button",value="Delayed"),timeout_ms=500)]))
            await r.play(saved["id"],{},operation_id="missing")
            await until(lambda:r.mode=="paused")
            assert "Target missing" in r.message
            await r.page.evaluate("""() => {const b=document.createElement('button');b.textContent='Delayed';b.onclick=()=>document.body.dataset.clicked='yes';document.body.append(b)}""")
            await r.resume()
            await until(lambda:r.mode=="completed")
            assert await r.page.locator("body").get_attribute("data-clicked")=="yes"
            # Pause during a wait; inserting the target must not click until resumed.
            await r.page.set_content("<p>Waiting</p>")
            await r.play(saved["id"],{})
            await r.pause()
            await r.page.evaluate("""() => {const b=document.createElement('button');b.textContent='Delayed';b.onclick=()=>document.body.dataset.clicked='yes';document.body.append(b)}""")
            await asyncio.sleep(.15)
            assert await r.page.locator("body").get_attribute("data-clicked") is None
            await r.stop()
            assert json.loads(r.store.journal.read_text())["status"]=="stopped"
            assert not r.busy() and r.page is None
        finally: await agent.close();await r.close()
    asyncio.run(run())


def test_missing_file_and_invalid_frame_rejected(tmp_path):
    bad=task([dict(action="click",locator=dict(by="id",value="button",frames=[dict(by="css",value="iframe:first-child")]))])
    with pytest.raises(Invalid):validate_task(bad)
    async def run():
        r=Runner(tmp_path,headless=True)
        saved=r.store.save(task([dict(action="upload",locator=dict(by="label",value="Choose PSD"),value={"file":str(uuid.uuid4())})]))
        with pytest.raises(Invalid): await r.play(saved["id"],{})
        assert r.context is None
    asyncio.run(run())


def test_frame_origin_and_missing_frame_are_bounded(tmp_path):
    async def run():
        r=Runner(tmp_path,headless=True)
        try:
            await r.open_browser()
            await r.page.route("http://fixture.invalid/**",lambda route:route.fulfill(
                body='<iframe title="External" src="http://other.invalid/"></iframe>',content_type="text/html"))
            await r.page.route("http://other.invalid/**",lambda route:route.fulfill(
                body='<button>External action</button>',content_type="text/html"))
            await r.page.goto("http://fixture.invalid/")
            await r.set_recording(True)
            await r.page.frame_locator('iframe[title="External"]').get_by_role("button").click()
            await r.set_recording(False)
            assert "same-origin" in r.draft["steps"][-1]["reason"]
            saved=r.store.save(task([dict(action="click",timeout_ms=500,locator=dict(
                by="role",role="button",value="Missing",frames=[dict(by="title",value="Missing frame")]))]))
            await r.play(saved["id"],{})
            await until(lambda:r.mode=="paused")
            assert "Step 1 of 1" in r.message
            await r.stop()
            assert json.loads(r.store.journal.read_text())["status"]=="stopped"
        finally:await r.close()
    asyncio.run(run())
