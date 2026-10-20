"""Full OS/auth/backend/outbound helper acceptance. Synthetic local PostgreSQL only."""
import asyncio
import json
from pathlib import Path
import sys
import subprocess
import threading
import time
from playwright.async_api import async_playwright
from task_recorder.server import Bridge

SITE="http://127.0.0.1:18961"
ROOT=Path.home()/"AppData/Local/SportsCaveOS/TaskRecorderPhase2-Acceptance-64cdf0b0"
ROOT.mkdir(parents=True,exist_ok=True)
(root_file:=ROOT/"example.txt").write_text("Synthetic file for recorder upload")
bridge=Bridge(ROOT,18931,preview=True)
thread=threading.Thread(target=bridge.serve_forever,daemon=True);thread.start()
helper_process=None

def submit(coro):return asyncio.run_coroutine_threadsafe(coro,bridge.loop)

async def demo_actions():
    r=bridge.runner;p=r.page
    await p.get_by_role("link",name="Start product form",exact=True).click()
    await p.get_by_label("Product name",exact=True).fill("Phase two A")
    await p.get_by_label("Headline",exact=True).fill("Local recording trial")
    await p.get_by_label("Destination URL",exact=True).fill("https://example.com/products?category=sport&page=2")
    await p.get_by_label("Category",exact=True).select_option("sport")
    r.file_selector=lambda:str(root_file)
    await p.get_by_label("Image",exact=True).click()
    await p.locator("#uploadStatus").filter(has_text="Upload ready").wait_for()
    await p.get_by_role("button",name="Reveal delayed content",exact=True).click()
    await p.get_by_role("button",name="Continue after delay",exact=True).click()
    await p.get_by_role("button",name="Save demo product",exact=True).click()
    return json.loads(await p.locator("#result").inner_text())

async def main():
    global bridge,thread,helper_process
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        page=await browser.new_page(viewport={"width":1366,"height":850})
        page.set_default_timeout(12000)
        await page.goto(SITE+"/?page=task_recorder")
        await page.get_by_placeholder("Username or email",exact=True).fill("recorder-preview@example.invalid")
        await page.get_by_placeholder("Password",exact=True).fill("RecorderPreview-Only-2026")
        await page.get_by_role("button",name="Sign in",exact=True).click()
        panel=page.frame_locator('iframe[src="/task-recorder/panel"]')
        await panel.locator("#pair").wait_for(state="attached")
        if not bridge.agent.credentials():
            await panel.locator("#pair").click()
            await panel.locator("#code").filter(has_text=__import__("re").compile(r"[A-Z2-9]{4}-")).wait_for()
            code=await panel.locator("#code").inner_text()
            local=await browser.new_page()
            await local.goto("http://127.0.0.1:18931/pair#"+__import__("urllib.parse",fromlist=["urlencode"]).urlencode({"origin":SITE,"code":code}))
            await local.get_by_label("PC name",exact=True).fill("Automated acceptance PC")
            await local.get_by_role("button",name="Continue",exact=True).click()
            await local.locator("#message").filter(has_text=__import__("re").compile(".+")).wait_for()
            print("PC approval check:",await local.locator("#message").inner_text(),flush=True)
            await local.get_by_role("button",name="Approve connection on this PC",exact=True).click()
            await local.locator("#message").filter(has_text="PC connected").wait_for()
            await local.close()
        await panel.locator("#pc").filter(has_text="Connected").wait_for(timeout=30000)
        print("PASS actual OS login, single-use challenge and explicit PC approval",flush=True)
        if await panel.locator("#stop").is_visible():
            await panel.locator("#stop").click()
            await panel.locator("#record").wait_for(state="visible")
        await panel.locator("#advanced > summary").click()
        await panel.locator("#website").fill("http://127.0.0.1:18931/demo?category=sport&page=2")
        await panel.locator("#advanced > summary").click()
        await panel.locator("#record").click()
        await panel.locator("#message").filter(has_text="Recording this browser").wait_for(timeout=25000)
        assert await panel.locator("#record").is_hidden()
        result=await asyncio.wrap_future(submit(demo_actions()))
        assert result["submissions"]==1,result
        await panel.locator("#stop").click()
        await panel.locator("#message").filter(has_text="Recording saved").wait_for(timeout=12000)
        await panel.locator("#play").wait_for(state="visible")
        assert bridge.runner.draft["name"].startswith("Recording ")
        assert any(s["action"]=="upload" and "file" in s["value"] for s in bridge.runner.draft["steps"])
        task_id=bridge.runner.draft["id"]
        await panel.locator("#play").click()
        await panel.locator("#message").filter(has_text="Playing").wait_for(timeout=12000)
        await panel.locator("#message").filter(has_text="Task completed").wait_for(timeout=20000)
        async def result_read():return json.loads(await bridge.runner.page.locator("#result").inner_text())
        assert (await asyncio.wrap_future(submit(result_read())))["submissions"]==1
        print("PASS OS Record > automatic save on Stop > exact Play, reused local upload, legitimate query URL",flush=True)

        # Actual modal close/reopen must recover the helper's current task/result.
        dialog=page.get_by_role("dialog")
        await dialog.get_by_role("button",name="Close",exact=True).click()
        await page.get_by_role("button",name="Open recorder",exact=True).click()
        panel=page.frame_locator('iframe[src="/task-recorder/panel"]')
        await panel.locator("#message").filter(has_text="Task completed").wait_for(timeout=10000)
        await panel.locator("#advanced > summary").click()
        await panel.locator("#inspect").click()
        await panel.locator("#detail").wait_for(state="visible")
        await panel.locator("#reusable").click()
        await panel.locator("#inputs input").first.wait_for()
        await panel.get_by_label("product name",exact=True).fill("Phase two B")
        await panel.locator("#play").click()
        await panel.locator("#message").filter(has_text="Playing").wait_for(timeout=12000)
        await panel.locator("#message").filter(has_text="Task completed").wait_for(timeout=20000)
        second=await asyncio.wrap_future(submit(result_read()))
        assert second["product"]=="Phase two B" and second["submissions"]==1,second
        print("PASS reopen modal, reusable labelled values and changed-input playback",flush=True)
        await page.screenshot(path=str(ROOT/"os-simple-flow.png"))

        # Repair tools still dispatch through the real authenticated OS route.
        await panel.locator("#inspect").click()
        task=json.loads(await panel.locator("#taskJson").input_value())
        task["steps"].append({"action":"wait","locator":{"by":"id","value":"missing-trial-target"},"timeout_ms":500})
        await panel.locator("#taskJson").locator("..").locator("summary").click()
        await panel.locator("#taskJson").fill(json.dumps(task))
        await panel.locator("#edit").click()
        await asyncio.sleep(2)
        await panel.locator("#play").click()
        await panel.locator("#message").filter(has_text="Target missing").wait_for(timeout=20000)
        await panel.locator("#resume").click()
        await panel.locator("#message").filter(has_text="Target missing").wait_for(timeout=10000)
        started=time.monotonic();await panel.locator("#stop").click()
        await panel.locator("#record").wait_for(state="visible",timeout=8000)
        assert time.monotonic()-started<8
        print("PASS missing target pauses, safe Resume and OS Stop",flush=True)

        # A long wait permits deterministic duplicate/start and network fault checks.
        task["steps"][-1]["timeout_ms"]=30000
        await panel.locator("#taskJson").fill(json.dumps(task));await panel.locator("#edit").click();await asyncio.sleep(2)
        await panel.locator("#play").click()
        await panel.locator("#message").filter(has_text="Playing").wait_for(timeout=12000)
        duplicate=await page.evaluate("""async device=>{const r=await fetch('/api/task-recorder/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device_id:device,id:crypto.randomUUID(),kind:'record',payload:{}})});return r.status;}""",bridge.agent.credentials()["device_id"])
        assert duplicate==409,duplicate
        async def lose_connection():await bridge.agent.client.aclose()
        await asyncio.wrap_future(submit(lose_connection()))
        deadline=time.monotonic()+8
        while bridge.runner.mode!="interrupted" and time.monotonic()<deadline:await asyncio.sleep(.1)
        assert bridge.runner.mode=="interrupted" and not bridge.runner.busy()
        print("PASS duplicate Start rejected and outbound connection loss interrupts without replay",flush=True)

        # Full helper shutdown/reinitialisation, keeping the same DPAPI credential.
        await asyncio.to_thread(bridge.shutdown);await asyncio.to_thread(bridge.close);thread.join()
        bridge=None
        installed=Path.home()/"AppData/Local/SportsCaveOS/TaskRecorderHelper"
        helper_python=installed/"venv/Scripts/python.exe"
        helper_process=subprocess.Popen([str(helper_python),"-m","task_recorder.server","--preview","--data-dir",str(ROOT)],
            cwd=installed/"app",creationflags=subprocess.CREATE_NO_WINDOW,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        await page.reload()
        panel=page.frame_locator('iframe[src="/task-recorder/panel"]')
        await panel.locator("#pc").filter(has_text="Connected").wait_for(timeout=30000)
        from task_recorder.windows import Vault
        from task_recorder.store import Store
        assert Vault(ROOT).read().get("device")
        assert Store(ROOT).get(task_id)
        print("PASS installed helper process restart reconnects without another pairing challenge; tasks persist",flush=True)

        # Same-origin actor and device auth reject unauthorised control requests.
        no_cookie=await pw.request.new_context()
        denied=await no_cookie.get(SITE+"/api/task-recorder/state");assert denied.status==403
        denied=await no_cookie.post(SITE+"/api/task-recorder/device/exchange",data={});assert denied.status==403
        denied=await page.request.post(SITE+"/api/task-recorder/pairing",headers={"Origin":"https://untrusted.invalid"},data={});assert denied.status==403
        await no_cookie.dispose()
        # Pair revoke is performed through the actual OS panel.
        await panel.locator("#advanced > summary").click()
        page.once("dialog",lambda d:asyncio.create_task(d.accept()))
        await panel.locator("#revoke").click()
        await panel.locator("#pc").filter(has_text="No PC connected").wait_for(timeout=25000)
        deadline=time.monotonic()+20
        while Vault(ROOT).read().get("device") and time.monotonic()<deadline:await asyncio.sleep(.2)
        assert not Vault(ROOT).read().get("device")
        print("PASS unauthorised account/device controls rejected and OS revoke invalidates helper",flush=True)
        (ROOT/"phase2-evidence.json").write_text(json.dumps({"os_login":True,"pairing":True,"record_stop_play":True,"file_reuse":True,"query_urls":True,"changed_input_result":second,"modal_recovery":True,"helper_restart_reconnect":True,"unauthorised_rejected":True,"revoke":True},indent=2))
        await browser.close()

try:asyncio.run(main())
finally:
    if bridge:
        bridge.shutdown();bridge.close();thread.join()
    if helper_process:
        subprocess.run([str(Path.home()/"AppData/Local/SportsCaveOS/TaskRecorderHelper/venv/Scripts/python.exe"),"-m","task_recorder.server","--shutdown","--data-dir",str(ROOT)],cwd=Path.home()/"AppData/Local/SportsCaveOS/TaskRecorderHelper/app",check=True,creationflags=subprocess.CREATE_NO_WINDOW)
        helper_process.wait(timeout=20)
