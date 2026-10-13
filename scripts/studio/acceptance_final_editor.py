"""Focused V9 final editor acceptance in a disposable Edge profile and isolated Docker.
Never reads device secrets or connects to the active companion.
"""
import hashlib
import json
import statistics
import threading
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import drafts, studio, draft_ui, source_editor, source_navigation

ROOT=Path(__file__).resolve().parents[2]
HOME=ROOT.parent
TASK="v9-final-editor"
OWNER="codex/core-editor-01a13432"
OUT=ROOT/"docs"/"final-editor-evidence"
OUT.mkdir(parents=True,exist_ok=True)
registry=studio.read(HOME/".studio/registry.json")
assigned=studio.task_by_id(registry,TASK,OWNER)
assert studio.identity(registry,assigned)==ROOT
draft=next((d for d in registry.get("drafts",[]) if d["task_id"]==TASK),None)
if not draft:draft=drafts.new(HOME,TASK,OWNER,"V9 final editor isolated acceptance")
draft_id=draft["id"]
paths=["components/sign_in/presentation.html","components/sign_in/presentation.css","orders_page.css"]
baseline={p:(ROOT/p).read_bytes() for p in paths}
original_app=(ROOT/"app.py").read_bytes()
server=draft_ui.DraftServer(HOME,TASK,OWNER,port=0)
assert server.server_port!=18762 and server.device is None
server_thread=threading.Thread(target=server.run,daemon=True)
server_thread.start()
report={"scope":"Only assigned isolated CORE worktree; disposable Edge; ephemeral QA HTTP port; no active 18762/task/trust changes",
        "checks":{},"timings":{},"browser_errors":[],"failures":[]}
def record(name,value=True):
    report["checks"][name]=value
    print(name,value,flush=True)
def revision():return next(d for d in studio.read(HOME/".studio/registry.json")["drafts"] if d["id"]==draft_id)["revision"]
try:
 with sync_playwright() as pw:
    browser=pw.chromium.launch(channel="msedge",headless=True)
    context=browser.new_context(viewport={"width":1680,"height":1050},permissions=["clipboard-read","clipboard-write"])
    page=context.new_page()
    page.on("pageerror",lambda e:report["browser_errors"].append(str(e)))
    dialogs=[]
    def no_discard_dialog(d):
        dialogs.append(d.message)
        d.dismiss()
    page.on("dialog",no_discard_dialog)
    started=time.perf_counter()
    page.goto(server.origin+"/workspace#token="+server.token)
    expect(page.locator("#ed-source")).to_be_visible(timeout=60000)
    report["timings"]["editor_ready_seconds"]=time.perf_counter()-started
    expect(page.locator("#ws-image")).to_be_visible(timeout=150000)
    expect(page.locator("#ws-loading")).to_be_hidden(timeout=150000)
    report["timings"]["cold_ready_seconds"]=time.perf_counter()-started
    container=server.preview_runtime.container_id
    record("existing_image_and_isolation_probes",server.preview_runtime.evidence["probe"]["passed"] and server.preview_runtime.evidence["browser"]["passed"])
    assert page.locator('[data-left-tab]').count()==0
    expect(page.locator("#ws-scope")).to_have_value("page")
    record("one_explorer_default_this_page")
    def settled():expect(page.locator("#ws-loading")).to_be_hidden(timeout=90000)
    def route(key):
        page.locator("#ws-page").select_option(key)
        expect(page.locator("#ws-page")).to_have_value(key)
        settled()
    def source(path):
        item=page.locator("#ws-list button").filter(has_text=path.split("/")[-1]).first
        item.click()
        expect(page.locator("#ed-path")).to_contain_text(path)
    def write(value):page.locator("#ed-source").fill(value)
    def inspect(target,alt=False):
        box=page.locator("#ws-image").bounding_box();frame=server.preview_runtime.last_frame
        if not alt:page.locator("#ws-inspect").click()
        if alt:page.keyboard.down("Alt")
        page.mouse.click(box["x"]+target["x"]*box["width"]/frame["width"],box["y"]+target["y"]*box["height"]/frame["height"])
        if alt:page.keyboard.up("Alt")
        settled()
        expect(page.locator("#ws-scope")).to_have_value("section")
        if not alt:page.locator("#ws-inspect").click()
    route("orders")
    expect(page.locator("#ed-path")).to_contain_text("orders_page.py")
    assert page.locator('#ws-list [data-path="orders_page.css"]').count()==1
    assert page.locator('#ws-list [data-path="ads_page.py"]').count()==0
    record("orders_relevant_sources_only")
    page.screenshot(path=str(OUT/"orders.png"),full_page=True)
    target=next(t for t in server.preview_runtime.last_frame["inspect_targets"] if t["tag"]=="input")
    inspect(target)
    expect(page.locator("#ed-path")).to_contain_text("orders_page.py")
    selected=page.locator("#ed-source").evaluate("n=>n.value.slice(n.selectionStart,n.selectionEnd)")
    assert "text_input" in selected
    page.locator("#ed-copy-section").click()
    expect(page.locator("#ed-status")).to_contain_text("section copied")
    copied=page.evaluate("navigator.clipboard.readText()")
    assert "orders_page.py" in copied and "text_input" in copied
    record("orders_search_exact_source_and_copy_section")
    page.locator("#ws-scope").select_option("page")
    # Normal clicks remain interactive and synchronize dropdown + primary source.
    nav=next(t for t in server.preview_runtime.last_frame["navigation_targets"] if t["page"]=="dashboard")
    box=page.locator("#ws-image").bounding_box();frame=server.preview_runtime.last_frame
    page.mouse.click(box["x"]+nav["x"]*box["width"]/frame["width"],box["y"]+nav["y"]*box["height"]/frame["height"])
    expect(page.locator("#ws-page")).to_have_value("dashboard",timeout=30000);settled()
    record("preview_navigation_synchronises_page_and_sources")
    expect(page.locator("#ed-path")).to_contain_text("app.py")
    assert page.locator('#ws-list [data-path="orders_page.css"]').count()==0
    heading=next(t for t in server.preview_runtime.last_frame["inspect_targets"] if "Events" in t.get("text",""))
    inspect(heading,alt=True)
    expect(page.locator("#ed-path")).to_contain_text("app.py")
    record("home_heading_verified_source")
    route("__signin__")
    expect(page.locator("#ed-path")).to_contain_text(paths[0])
    target=next(t for t in server.preview_runtime.last_frame["inspect_targets"] if t["component"]=="title")
    inspect(target)
    expect(page.locator("#ed-path")).to_contain_text("signin_presentation.py")
    selected=page.locator("#ed-source").evaluate("n=>n.value.slice(n.selectionStart,n.selectionEnd)")
    assert "TITLE =" in selected
    page.locator("#ed-copy-related").click()
    expect(page.locator("#ed-status")).to_contain_text("related files copied")
    copied=page.evaluate("navigator.clipboard.readText()")
    assert all(p in copied for p in paths[:2]) and "signin_presentation.py" in copied
    record("signin_title_setting_and_copy_related")
    panel=next(t for t in server.preview_runtime.last_frame["inspect_targets"] if t["component"]=="panel")
    # Click visible panel padding, not the heading child.
    panel=dict(panel,x=max(5,panel["x"]-80),y=panel["y"]+35)
    inspect(panel)
    expect(page.locator("#ed-path")).to_contain_text("components/sign_in/presentation.html")
    record("signin_panel_mapping")
    route("ads")
    targets=server.preview_runtime.last_frame["inspect_targets"]
    inspect(next(t for t in targets if t["tag"] in ("h1","h2","h3","button")))
    assert "Verified" in page.locator("#ed-status").inner_text() or "source" in page.locator("#ed-status").inner_text()
    record("ads_verified_source_or_honest_fallback")
    page.locator("#ws-scope").select_option("all")
    assert page.locator('#ws-list [data-path="orders_page.css"]').count()==1
    assert page.locator('#ws-list [data-path="ads_page.py"]').count()==1
    record("all_files_authorised_tree")
    source(paths[0]);html=page.locator("#ed-source").input_value()
    page.locator("#ed-copy").click();expect(page.locator("#ed-status")).to_contain_text("Complete source copied")
    assert page.evaluate("navigator.clipboard.readText()").replace("\r\n","\n")==html
    write(html.replace("{{title}}","V9 final editor acceptance"))
    route("orders");source(paths[2]);css=page.locator("#ed-source").input_value();write(css+"\n/* V9 isolated acceptance */\n")
    expect(page.locator("#ws-unsaved")).to_have_text("Unsaved files: 2")
    for key in ("dashboard","ads","orders","__signin__"):
        route(key);assert page.locator('#ws-list [data-path="orders_page.css"]').count()>=1
    assert not dialogs,dialogs
    record("multi_file_buffers_survive_navigation_without_discard")
    # Local undo and redo retain independent changes.
    source(paths[0]);page.locator("#ws-undo").click();expect(page.locator("#ed-source")).to_have_value(html)
    page.locator("#ws-redo").click();expect(page.locator("#ed-source")).to_have_value(html.replace("{{title}}","V9 final editor acceptance"))
    record("undo_redo")
    # Reload only this disposable QA page to exercise all buffer recovery.
    page.remove_listener("dialog",no_discard_dialog);page.on("dialog",lambda d:d.accept())
    page.goto(server.origin+"/workspace#token="+server.token)
    expect(page.locator("#ws-unsaved")).to_have_text("Unsaved files: 2",timeout=60000);settled()
    record("unsaved_buffer_recovery")
    before=revision();started=time.perf_counter();page.locator("#ws-save").click()
    expect(page.locator("#ed-status")).to_contain_text("Saved all files in draft revision",timeout=120000)
    expect(page.locator("#ws-unsaved")).to_have_text("All files saved")
    assert revision()==before+1
    assert "V9 final editor acceptance" in server.preview_runtime.last_frame["text"]
    assert server.preview_runtime.container_id==container
    report["timings"]["save_all_preview_seconds"]=time.perf_counter()-started
    record("single_save_all_revision_preview_reflects_html_same_container")
    # Backend protects source and concurrent writes.
    for changes in ([{"path":"app.py","expected_hash":"0"*64,"source":"replacement"}],
                    [{"path":paths[2],"expected_hash":"0"*64,"source":css}]):
        try:source_editor.write_all(HOME,draft_id,OWNER,revision(),changes)
        except (ValueError,RuntimeError):pass
        else:raise AssertionError("Unauthorised or conflicting write accepted")
    record("readonly_permissions_and_hash_conflicts")
    # The synthetic ledger is intentionally empty: verify table DOM/key resolution
    # in a labelled fixture, rather than claiming a nonexistent live table was clicked.
    from isolation.source_inspection import INSPECT
    scratch=context.new_page()
    scratch.set_content('<div class="st-key-orders-table"><table><tr><th>Order</th></tr><tr><td>SYNTHETIC-ONLY</td></tr></table></div><input value="never-export-input-values">')
    rect=scratch.locator("table").bounding_box()
    hit=scratch.evaluate(INSPECT,{"x":int(rect["x"]+5),"y":int(rect["y"]+5)})
    mapped=source_navigation.resolve(ROOT,"orders",hit,draft_id,revision())
    assert mapped["location"]["path"]=="orders_page.py" and not mapped["exact"]
    assert "enclosing" in mapped["reason"]
    scratch.close()
    record("orders_table_dom_fixture_verified_enclosing_source")
    assert (ROOT/"app.py").read_bytes()==original_app
    record("app_py_never_replaced")
    latencies=[]
    for _ in range(10):
        started=time.perf_counter();source_navigation.page_model(ROOT,"orders",draft_id,revision());latencies.append((time.perf_counter()-started)*1000)
    report["timings"]["warm_mapping_median_ms"]=statistics.median(latencies[1:])
    page.screenshot(path=str(OUT/"editor-preview.png"),full_page=True)
    browser.close()
except Exception as error:
    report["failures"].append(type(error).__name__+": "+str(error))
    if server.preview_runtime and server.preview_runtime.last_frame:
        report["last_frame"]={k:v for k,v in server.preview_runtime.last_frame.items() if k!="image"}
    try:
        page.screenshot(path=str(OUT/"failure.png"),full_page=True)
        report["visible_error"]=page.locator("body").inner_text()[:2000]
    except Exception:pass
    raise
finally:
    server.stopping=True
    server_thread.join(timeout=30)
    assert not server_thread.is_alive(), "QA server did not stop before source restoration"
    rows=[]
    for path,data in baseline.items():
        opened=source_editor.open_file(HOME,draft_id,OWNER,path)
        if (ROOT/path).read_bytes()!=data:rows.append({"path":path,"expected_hash":opened["hash"],"source":data.decode("utf-8-sig")})
    if rows:source_editor.write_all(HOME,draft_id,OWNER,revision(),rows)
    assert all((ROOT/path).read_bytes()==data for path,data in baseline.items())
    report["source_restored"]=True
    (OUT/"acceptance.json").write_text(json.dumps(report,indent=2),encoding="utf-8")

