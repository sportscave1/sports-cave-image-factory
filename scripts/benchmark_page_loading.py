"""Paired real-renderer loading tests with synthetic reads, on loopback only."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import tempfile
import time

from benchmark_app_startup import ROOT,fixture_server


def start_measure(page,selector):
    page.evaluate("""selector=>{
      window.__pageMeasure?.observer?.disconnect();
      const m=window.__pageMeasure={started:performance.now(),ready:null};
      let scheduled=false;
      const check=()=>{
        scheduled=false;
        const el=document.querySelector(selector);
        const grid=selector.startsWith('#orders-ready')?document.querySelector('[data-testid="stDataFrame"]'):null;
        if(el && (!selector.startsWith('#orders-ready') || grid?.getBoundingClientRect().height>0)){
          m.ready=performance.now();m.observer.disconnect();
        }
      };
      m.observer=new MutationObserver(()=>{
        if(!scheduled){scheduled=true;requestAnimationFrame(check);}
      });
      m.observer.observe(document.body,{subtree:true,childList:true,attributes:true});
    }""",selector)


def elapsed_ready(page):
    page.wait_for_function("window.__pageMeasure?.ready!==null")
    return page.evaluate("window.__pageMeasure.ready-window.__pageMeasure.started")


def assert_orders_style_layout(page, *, mobile=False):
    state=page.evaluate("""() => {
      const style=[...document.querySelectorAll('[data-testid="stMarkdownContainer"] > style')]
        .find(s=>s.textContent.includes('.st-key-orders_search_text'));
      const owner=style?.closest('[data-testid="stElementContainer"]');
      const main=document.querySelector('[data-testid="stMainBlockContainer"]');
      return {owned:!!owner, height:owner?.getBoundingClientRect().height,
        padding:parseFloat(getComputedStyle(main).paddingTop)};
    }""")
    assert state["owned"], "Orders CSS escaped its fragment-owned element"
    assert state["height"]==0, "Orders CSS reserved a blank layout slot"
    assert state["padding"]==(78 if mobile else 72), "Orders CSS did not apply"
    return state


def run(args):
    from playwright.sync_api import sync_playwright
    sources=["app.py","home_fast.py","display_snapshot.py","orders_page.py","orders_page.css"]
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources}
    results=[]
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="page-loading-",dir=args.out.parent) as folder:
        with fixture_server(Path(folder),fixture="page_loading_measurement") as (url,healthy,log):
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,channel=args.browser_channel,args=[
                    "--proxy-server=http://127.0.0.1:1","--proxy-bypass-list=127.0.0.1;localhost",
                    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"])
                try:
                    for index in range(args.samples):
                        for mode in (["before","after"] if index%2==0 else ["after","before"]):
                            for route,delay in [("Home",.3),("Orders",.3),("Orders",1.4)]:
                                context=browser.new_context(viewport=dict(width=1440,height=1000),service_workers="block")
                                page=context.new_page()
                                errors=[]
                                page.on("pageerror",lambda error:errors.append(str(error)))
                                try:
                                    page.goto(f"{url}/?mode={mode}&delay={delay}",wait_until="domcontentloaded")
                                    page.locator("#other-ready").wait_for()
                                    prior=int(page.locator("#fixture-runs").inner_text())
                                    marker="#home-ready" if route=="Home" else "#orders-ready"
                                    start_measure(page,marker)
                                    page.get_by_text(route,exact=True).click()
                                    page.locator(marker).wait_for(timeout=20000)
                                    elapsed=elapsed_ready(page)
                                    runs=int(page.locator(marker).get_attribute("data-runs"))
                                    if mode=="after" and runs-prior!=1:
                                        raise AssertionError("Loading completion caused an extra app rerun.")
                                    record=dict(mode=mode,route=route,simulated_read_seconds=delay,
                                        ready_ms=round(elapsed,3),full_app_runs_for_navigation=runs-prior)
                                    if route=="Orders":
                                        assert page.locator("#orders-ready").get_attribute("data-row-count")=="150"
                                        prior_runs=page.locator("#fixture-runs").inner_text()
                                        page.get_by_label("Search orders").fill("alpha")
                                        start_measure(page,'#orders-ready[data-query="alpha"]')
                                        page.get_by_test_id("stBaseButton-secondaryFormSubmit").click()
                                        if mode=="after" and delay>1:
                                            page.get_by_text("Updating orders…",exact=True).wait_for()
                                            record["previous_rows_visible_during_search"]=page.get_by_test_id("stDataFrame").is_visible()
                                            assert record["previous_rows_visible_during_search"]
                                        page.locator('#orders-ready[data-query="alpha"]').wait_for(timeout=20000)
                                        record["search_ms"]=round(elapsed_ready(page),3)
                                        record["search_full_app_reruns"]=int(page.locator("#fixture-runs").inner_text())-int(prior_runs)
                                        if mode=="after":
                                            assert record["search_full_app_reruns"]==0
                                            record["orders_styles"]=assert_orders_style_layout(page)
                                    page.set_viewport_size(dict(width=390,height=844))
                                    if route=="Orders" and mode=="after":
                                        record["mobile_orders_styles"]=assert_orders_style_layout(page,mobile=True)
                                    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                                    assert not page.get_by_test_id("stException").count(),page.get_by_test_id("stException").all_inner_texts()
                                    assert not errors,errors
                                    results.append(record)
                                    print(json.dumps(record),flush=True)
                                except Exception:
                                    args.out.with_suffix(".error.log").write_text(
                                        page.locator("body").inner_text()+"\n"+log.read_text(encoding="utf-8"),encoding="utf-8")
                                    raise
                                finally:
                                    context.close()
                    # Leave during a deliberately slow read. It must neither
                    # delay navigation nor render a late result into Other.
                    for route in ("Home","Orders"):
                        context=browser.new_context(viewport=dict(width=1440,height=1000))
                        page=context.new_page()
                        try:
                            page.goto(f"{url}/?mode=after&delay=2")
                            page.locator("#other-ready").wait_for()
                            page.get_by_text(route,exact=True).click()
                            if route=="Home":
                                page.get_by_text("Saved Home section · loading saved information…").wait_for()
                            else:
                                page.get_by_role("heading",name="Orders",exact=True).wait_for()
                            previous=int(page.locator("#fixture-runs").inner_text())
                            marker=f'#other-ready[data-runs="{previous+1}"]'
                            start_measure(page,marker)
                            page.get_by_text("Other",exact=True).click()
                            page.locator(marker).wait_for(timeout=5000)
                            elapsed=elapsed_ready(page)
                            if elapsed>600:raise AssertionError(f"{route} blocked departure: {elapsed} ms")
                            page.wait_for_timeout(2200)
                            assert page.locator("#home-ready").count()==0
                            assert page.locator("#orders-ready").count()==0
                            assert page.locator("#orders-ack").count()==0
                            assert not page.get_by_test_id("stException").count()
                            results.append(dict(mode="after",route=route,departure_ms=round(elapsed,3)))
                        finally:
                            context.close()
                    # The new Home retry is a native fragment interaction.
                    context=browser.new_context(viewport=dict(width=1440,height=1000))
                    page=context.new_page()
                    try:
                        page.goto(f"{url}/?mode=after&delay=.2&fail_first=1")
                        page.locator("#other-ready").wait_for()
                        page.get_by_text("Home",exact=True).click()
                        page.get_by_role("button",name="Retry Saved Home section",exact=True).wait_for()
                        runs=page.locator("#fixture-runs").inner_text()
                        page.get_by_role("button",name="Retry Saved Home section",exact=True).click()
                        page.locator("#home-ready").wait_for()
                        assert page.locator("#home-ready").inner_text()=="2"
                        assert page.locator("#fixture-runs").inner_text()==runs
                        assert not page.get_by_test_id("stException").count()
                        results.append(dict(mode="after",route="Home",check="failure_retry",reads=2,
                                            completion_full_app_reruns=0))
                    finally:
                        context.close()
                finally:
                    browser.close()
            server_log=log.read_text(encoding="utf-8")
    for name,digest in hashes.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,"Measured source changed"
    groups=defaultdict(list)
    for row in results:
        if "ready_ms" in row:groups[(row["mode"],row["route"],row["simulated_read_seconds"])].append(row["ready_ms"])
    summary=[dict(mode=mode,route=route,simulated_read_seconds=delay,n=len(values),
                  median_ms=round(statistics.median(values),3),range_ms=[min(values),max(values)])
             for (mode,route,delay),values in groups.items()]
    evidence=dict(scope="Actual Home/Orders loading functions with synthetic read/presentation; not production TTI",
                  source_sha256=hashes,results=results,summary=summary,server_log=server_log)
    args.out.write_text(json.dumps(evidence,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--samples",type=int,default=3)
    parser.add_argument("--browser-channel",default=None)
    args=parser.parse_args()
    if args.samples<1:parser.error("Use a positive sample count.")
    run(args)
