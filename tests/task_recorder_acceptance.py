"""Real-browser synthetic acceptance. Two invocations prove persistence across process restart.
Usage: python -m tests.task_recorder_acceptance record|replay DATA_DIR [--headless]
"""
import asyncio
import json
import sys
import threading
import time
from pathlib import Path
from task_recorder.server import Bridge
from task_recorder.schema import Invalid
from task_recorder.store import atomic

phase, directory = sys.argv[1:3]
root = Path(directory)
root.mkdir(parents=True,exist_ok=True)
server=Bridge(root,18941,headless="--headless" in sys.argv)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
r=server.runner
base=server.origin

async def wait_mode(mode,timeout=12):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if r.mode==mode:return
        await asyncio.sleep(.05)
    raise AssertionError("Expected "+mode+"; got "+r.mode+": "+r.message)

async def settle():
    await asyncio.sleep(.2)

async def record():
    await r.open_browser(base+"/demo")
    await r.command("record",{"task":{**r.blank(),"name":"Name entered before Record"}})
    assert r.draft["name"]=="Name entered before Record"
    p=r.page
    await p.get_by_role("link",name="Start product form",exact=True).click()
    await settle()
    await p.get_by_label("Product name",exact=True).fill("Product A")
    await p.get_by_label("Headline",exact=True).fill("First headline")
    await p.get_by_label("Destination URL",exact=True).fill("https://example.com/product-a")
    await p.get_by_label("Category",exact=True).select_option("sport")
    (root/"demo-a.txt").write_text("Synthetic upload A",encoding="utf-8")
    await p.get_by_label("Image",exact=True).set_input_files(str(root/"demo-a.txt"))
    await p.get_by_label("Approved",exact=True).check()
    await p.get_by_role("button",name="Reveal delayed content",exact=True).click()
    await p.get_by_role("button",name="Continue after delay",exact=True).click()
    await p.get_by_role("button",name="Save demo product",exact=True).click()
    await settle()
    await r.set_recording(False)
    task=r.draft
    task["name"]="Local product demonstration"
    # Repeated acceptance runs update the same synthetic example.
    if (root/"acceptance-task.json").exists():
        task["id"]=json.loads((root/"acceptance-task.json").read_text())["id"]
    mapping={"Product name":"product_name","Headline":"headline","Destination URL":"url"}
    for step in task["steps"]:
        if step["action"]=="fill" and step["locator"]["value"] in mapping:
            name=mapping[step["locator"]["value"]]
            step["value"]={"input":name}
            task["inputs"].append({"name":name,"required":True})
    assert len(task["steps"])>=10,task
    assert not any(s["action"]=="unsupported" for s in task["steps"]),task
    task=r.store.save(task)
    atomic(root/"acceptance-task.json",{"id":task["id"],"steps":len(task["steps"])})
    result=json.loads(await p.locator("#result").inner_text())
    assert result["product"]=="Product A" and result["submissions"]==1,result
    preview=await r.preview()
    assert not preview["blocked"] and preview["boxes"]
    assert "Product A" not in json.dumps(preview)
    # Exercise the actual UI, not just static markup. Only synthetic data is visible.
    browser=await r.pw.chromium.launch(headless=True)
    ui=await browser.new_page(viewport={"width":1366,"height":850})
    started=time.monotonic()
    await ui.goto(base+"/#key="+server.token)
    await ui.get_by_text("Local runner connected",exact=False).wait_for()
    load_ms=round((time.monotonic()-started)*1000)
    await ui.get_by_role("button",name="Local product demonstration",exact=False).click()
    await ui.get_by_label("Input value 1",exact=True).fill(str(root/"demo-a.txt"))
    await ui.get_by_role("button",name="Refresh",exact=True).click()
    await ui.locator("#previewNote").filter(has_text="Refreshed").wait_for()
    await ui.screenshot(path=str(root/"ui-1366.png"))
    assert await ui.locator("body").evaluate("e=>e.scrollWidth<=innerWidth"),"Horizontal overflow"
    assert await ui.locator("body").evaluate("e=>e.scrollHeight<=innerHeight"),"Desktop vertical overflow"
    await ui.set_viewport_size({"width":1920,"height":1080})
    await ui.screenshot(path=str(root/"ui-1920.png"))
    await ui.set_viewport_size({"width":1366,"height":768})
    await ui.screenshot(path=str(root/"ui-1366-768.png"))
    assert await ui.locator("body").evaluate("e=>e.scrollHeight<=innerHeight"),"Compact desktop vertical overflow"
    await browser.close()
    atomic(root/"record-evidence.json",{"phase":"record","steps":len(task["steps"]),"result":result,"ui_ready_ms":load_ms,"layout_preview_boxes":len(preview["boxes"]),"headed":not r.headless})
    print("PASS recorded, parameterized, named and saved; UI verified; "+str(len(task["steps"]))+" steps; ready "+str(load_ms)+"ms")

async def replay():
    task_id=json.loads((root/"acceptance-task.json").read_text())["id"]
    assert r.store.get(task_id)["name"]=="Local product demonstration"
    (root/"demo-b.txt").write_text("Synthetic upload B",encoding="utf-8")
    values={"product_name":"Product B","headline":"Different headline","url":"https://example.com/product-b","image_path":str(root/"demo-b.txt")}
    try:await r.play(task_id,{})
    except Invalid:pass
    else:raise AssertionError("Missing inputs were accepted")
    await r.play(task_id,values)
    try:await r.play(task_id,values)
    except Invalid:pass
    else:raise AssertionError("Concurrent task was accepted")
    await wait_mode("completed")
    result=json.loads(await r.page.locator("#result").inner_text())
    assert result=={"product":"Product B","headline":"Different headline","url":"https://example.com/product-b","category":"sport","approved":True,"file":"demo-b.txt","submissions":1},result
    # Drive Save/Play through the real console and authenticated HTTP bridge.
    browser=await r.pw.chromium.launch(headless=True)
    ui=await browser.new_page(viewport={"width":1366,"height":768})
    await ui.goto(base+"/#key="+server.token)
    await ui.get_by_role("button",name="Local product demonstration",exact=False).click()
    for n,value in enumerate([str(root/"demo-b.txt"),"Product C","Console playback","https://example.com/product-c"],1):
        await ui.get_by_label("Input value "+str(n),exact=True).fill(value)
    await ui.get_by_role("button",name="Save",exact=True).click()
    await ui.locator("#progress").filter(has_text="Task saved locally").wait_for()
    await ui.get_by_role("button",name="Play",exact=False).click()
    await ui.locator("#progress").filter(has_text="Task completed").wait_for(timeout=15000)
    console_result=json.loads(await r.page.locator("#result").inner_text())
    assert console_result["product"]=="Product C" and console_result["submissions"]==1,console_result
    await browser.close()

    def task(steps,name):
        return r.store.save({"version":1,"name":name,"inputs":[],"steps":steps})
    nav={"action":"navigate","value":base+"/demo/form"}
    missing={"action":"click","locator":{"by":"role","role":"button","value":"Not here"},"timeout_ms":700}
    t=task([nav,missing],"Missing target")
    await r.play(t["id"],{})
    await wait_mode("paused")
    assert "missing" in r.message and r.can_resume,r.message
    # Repair only the synthetic page; Resume must retry current step, not navigate.
    await r.page.evaluate("()=>{let b=document.createElement('button');b.textContent='Not here';b.onclick=()=>document.body.dataset.repaired='yes';document.body.append(b)}")
    await r.resume()
    await wait_mode("completed")
    assert await r.page.locator("body").get_attribute("data-repaired")=="yes"

    # Ambiguous targets pause before either button is clicked.
    await r.page.evaluate("()=>{for(let i=0;i<2;i++){let b=document.createElement('button');b.textContent='Duplicate';document.body.append(b)}}")
    ambiguous=task([{"action":"click","locator":{"by":"role","role":"button","value":"Duplicate"}}],"Ambiguous target")
    await r.play(ambiguous["id"],{})
    await wait_mode("paused")
    assert "ambiguous" in r.message
    await r.stop()

    # Pause during a condition wait; continue only after explicit Resume.
    pausing=task([nav,{"action":"wait","locator":{"by":"id","value":"manual-ready"},"timeout_ms":10000},
                  {"action":"fill","locator":{"by":"label","value":"Product name"},"value":"After resume"}],"Pause test")
    await r.play(pausing["id"],{})
    deadline=time.monotonic()+5
    while r.index<1 and time.monotonic()<deadline:await asyncio.sleep(.05)
    await r.pause()
    await r.page.evaluate("()=>{const e=document.createElement('p');e.id='manual-ready';e.textContent='Ready';document.body.append(e)}")
    await asyncio.sleep(.35)
    assert await r.page.get_by_label("Product name",exact=True).input_value()==""
    await r.resume()
    await wait_mode("completed")
    assert await r.page.get_by_label("Product name",exact=True).input_value()=="After resume"

    stopping=task([nav,{"action":"wait","locator":{"by":"id","value":"never-appears"},"timeout_ms":30000}],"Stop test")
    await r.play(stopping["id"],{})
    deadline=time.monotonic()+5
    while r.index<1 and time.monotonic()<deadline:await asyncio.sleep(.05)
    started=time.monotonic();await r.stop();stop_ms=round((time.monotonic()-started)*1000)
    assert stop_ms<3000 and not r.context and r.mode=="stopped",stop_ms
    # Automatic sign-in pause: neither username nor password enters the draft/preview.
    await r.command("new",{})
    await r.open_browser(base+"/demo")
    await r.set_recording(True)
    await r.page.get_by_role("link",name="Sign-in safety fixture",exact=True).click()
    await settle()
    assert r.mode=="recording_paused",r.state()
    await r.page.get_by_label("Username",exact=True).fill("DO_NOT_RECORD_USERNAME")
    await r.page.get_by_label("Password",exact=True).fill("DO_NOT_RECORD_PASSWORD")
    assert "DO_NOT_RECORD" not in json.dumps(r.state())
    assert (await r.preview())["blocked"]
    await r.page.get_by_role("button",name="Return to demo",exact=True).click()
    await r.resume()
    assert r.recording
    # Explicit unsupported keyboard action.
    await r.page.get_by_role("link",name="Start product form",exact=True).click()
    await settle()
    await r.page.get_by_label("Product name",exact=True).press("Enter")
    await settle()
    await r.set_recording(False)
    assert any(s["action"]=="unsupported" for s in r.draft["steps"])
    # An iframe present before Record must be flagged when interacted with.
    await r.command("new",{})
    await r.page.evaluate("()=>{const frame=document.createElement('iframe');frame.id='embedded-demo';frame.src='/demo/form';document.body.append(frame)}")
    embedded=r.page.frame_locator("#embedded-demo")
    await embedded.get_by_label("Product name",exact=True).wait_for()
    await r.set_recording(True)
    await embedded.get_by_label("Product name",exact=True).fill("Frame content must not be saved")
    await embedded.get_by_role("button",name="Reveal delayed content",exact=True).click()
    await settle()
    await r.set_recording(False)
    assert any(s["action"]=="unsupported" for s in r.draft["steps"])
    assert "Frame content must not be saved" not in json.dumps(r.draft)
    atomic(root/"replay-evidence.json",{"phase":"replay-after-process-restart","result":result,"console_result":console_result,"missing_target":"passed","ambiguity":"passed","pause_resume":"passed","stop_ms":stop_ms,"sign_in_privacy":"passed","unsupported_action":"passed","required_inputs":"passed","single_run":"passed","headed":not r.headless})
    print("PASS restarted, replayed Product B exactly once; pause/resume, stop ("+str(stop_ms)+"ms), missing/ambiguous targets, privacy, unsupported action, validation")

try:
    asyncio.run_coroutine_threadsafe(record() if phase=="record" else replay(),server.loop).result(timeout=120)
finally:
    server.shutdown();server.close();thread.join()
