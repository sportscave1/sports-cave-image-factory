"""Repeatable, loopback-only browser startup evidence with no production launch.

Creates a child with an allowlisted environment and a private temporary cwd.
Reports framework/transport timings and explicitly labelled simulated I/O.
Never opens the real app, provider APIs, credentials or customer databases.
"""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]

OBSERVER = """(() => {
  const state = window.__startupEvidence = {shellMs:null, readyMs:null, longTasks:[]};
  try {new PerformanceObserver(list => {
    for (const e of list.getEntries()) state.longTasks.push({startMs:e.startTime, durationMs:e.duration});
  }).observe({type:'longtask',buffered:true});} catch (_) {}
  const observer = new MutationObserver(() => {
    if(state.shellMs===null && document.querySelector('#startup-shell')) state.shellMs=performance.now();
    if(state.readyMs===null && document.querySelector('#startup-ready')) state.readyMs=performance.now();
  });
  observer.observe(document,{subtree:true,childList:true});
})();"""

SNAPSHOT = r"""() => {
  const nav=performance.getEntriesByType('navigation')[0];
  const ready=document.querySelector('#startup-ready');
  return { ...window.__startupEvidence,
    navigation:{ttfbMs:nav.responseStart-nav.startTime, domContentLoadedMs:nav.domContentLoadedEventEnd,
      responseEndMs:nav.responseEnd, type:nav.type,
      serverTiming:nav.serverTiming.map(e=>({name:e.name,duration:e.duration}))},
    paint:performance.getEntriesByType('paint').map(e=>({name:e.name,startMs:e.startTime})),
    assets:performance.getEntriesByType('resource').filter(e=>/\/static\/(js|css)\//.test(e.name))
      .map(e=>({path:new URL(e.name).pathname,transferBytes:e.transferSize,
        encodedBytes:e.encodedBodySize,decodedBytes:e.decodedBodySize,durationMs:e.duration,
        serverTiming:e.serverTiming.map(s=>({name:s.name,duration:s.duration}))})),
    simulated:{authMs:Number(ready.dataset.authMs),authCached:ready.dataset.authCached==='true',
      dataMs:Number(ready.dataset.dataMs),scriptMs:Number(ready.dataset.scriptMs)}
  };
}"""


def summary(values):
    ordered = sorted(values)
    return dict(n=len(values), p50_ms=round(statistics.median(ordered), 3),
                p95_ms=round(ordered[math.ceil(len(ordered)*.95)-1], 3))


def child_environment():
    allowed = {"SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP",
               "LOCALAPPDATA", "APPDATA", "USERPROFILE", "PROGRAMFILES", "PROGRAMFILES(X86)"}
    return {**{k:v for k,v in os.environ.items() if k.upper() in allowed},
            "PYTHONIOENCODING":"utf-8", "PYTHONDONTWRITEBYTECODE":"1"}


@contextmanager
def fixture_server(runtime, *, fixture="startup_measurement"):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    logfile = runtime / "server.log"
    began = time.perf_counter()
    with logfile.open("w", encoding="utf-8") as log:
        child = subprocess.Popen([sys.executable, "-B", str(ROOT / "scripts/startup_fixture_server.py"),
                                  "--port", str(port), "--fixture", fixture], cwd=runtime, env=child_environment(),
                                 stdout=log, stderr=subprocess.STDOUT,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            url = f"http://127.0.0.1:{port}"
            health = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            while True:
                if child.poll() is not None:
                    raise RuntimeError("Fixture failed; inspect local server.log.")
                try:
                    with health.open(url + "/_stcore/health", timeout=.5) as response:
                        if response.status == 200:
                            break
                except (OSError, urllib.error.URLError):
                    pass
                if time.perf_counter()-began > 30:
                    raise TimeoutError("Offline fixture did not become healthy.")
                time.sleep(.05)
            yield url, round((time.perf_counter()-began)*1000, 3), logfile
        finally:
            child.terminate()
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=8)


def browser_sample(browser, url, *, slow=False, gzip_only=False):
    context = browser.new_context(viewport=dict(width=1440, height=1000), service_workers="block",
                                  extra_http_headers={"Accept-Encoding": "gzip"} if gzip_only else {})
    context.add_init_script(OBSERVER)
    errors, external_requests = [], []
    # Do not use Playwright routing: it disables the browser HTTP cache.
    # Chromium's dead external proxy + loopback bypass enforce isolation.
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external_requests.append(request.url)
            if urlsplit(request.url).scheme in {"http","https"}
            and urlsplit(request.url).hostname != "127.0.0.1" else None)
    cdp = context.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send("Network.setBlockedURLs", {"urls":["https://*"]})
    encodings, sockets = {}, {}
    cdp.on("Network.webSocketCreated", lambda e: sockets.update({
        e["requestId"]:dict(createdMs=time.perf_counter()*1000)}))
    cdp.on("Network.webSocketHandshakeResponseReceived", lambda e: sockets[e["requestId"]].update(
        acceptedMs=time.perf_counter()*1000) if e["requestId"] in sockets else None)
    def response_received(event):
        response = event["response"]
        if "/static/js/" in response["url"] or "/static/css/" in response["url"]:
            headers = {k.lower():v for k,v in response["headers"].items()}
            encodings[urlsplit(response["url"]).path] = dict(
                encoding=headers.get("content-encoding", "identity"),
                cacheControl=headers.get("cache-control", ""), fromDiskCache=response.get("fromDiskCache",False))
    cdp.on("Network.responseReceived", response_received)
    if slow:
        cdp.send("Emulation.setCPUThrottlingRate", {"rate":4})
        cdp.send("Network.emulateNetworkConditions", dict(offline=False,latency=150,
            downloadThroughput=200000,uploadThroughput=100000))
    try:
        def navigate(reload=False):
            encodings.clear()
            sockets.clear()
            began = time.perf_counter()
            if reload:
                page.reload(wait_until="domcontentloaded", timeout=60000)
            else:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.locator('#startup-ready[data-route="Home"]').wait_for(timeout=60000)
            page.get_by_test_id("stMetric").first.wait_for()
            data = page.evaluate(SNAPSHOT)
            data["usableMs"] = round((time.perf_counter()-began)*1000, 3)
            data["assetHeaders"] = dict(encodings)
            handshake = next(iter(sockets.values()), {})
            data["websocketHandshakeMs"] = (round(handshake["acceptedMs"]-handshake["createdMs"], 3)
                if "acceptedMs" in handshake else None)
            data["websocketCreatedMs"] = round(handshake["createdMs"]-began*1000,3) if handshake else None
            data["websocketAcceptedMs"] = round(handshake["acceptedMs"]-began*1000,3) if "acceptedMs" in handshake else None
            return data
        cold = navigate()
        reopened = navigate(reload=True)
        if not cold["assets"] or sum(a["transferBytes"] for a in cold["assets"]) <= 0:
            raise AssertionError("A fresh browser must really download frontend bundles.")
        for asset in cold["assets"]:
            headers = cold["assetHeaders"].get(asset["path"], {})
            if asset["decodedBytes"] > 1024 and headers.get("encoding") not in {"gzip", "br"}:
                raise AssertionError("Large framework bundle was not compressed.")
            if "immutable" not in headers.get("cacheControl", ""):
                raise AssertionError("Framework bundle lost its immutable cache policy.")
        if sum(a["transferBytes"] for a in reopened["assets"]) != 0:
            raise AssertionError("Cached reload unexpectedly transferred JS/CSS bundles.")
        if not any(s["name"] == "os_headers" for s in cold["navigation"]["serverTiming"]):
            raise AssertionError("Initial-document server timing is missing.")
        transitions = []
        for route in ["Orders","Home","Orders","Home"]:
            began = time.perf_counter()
            previous = page.locator("#startup-ready").get_attribute("data-run")
            page.get_by_text(route, exact=True).click()
            page.wait_for_function("""([route,run])=>{
              const e=document.querySelector('#startup-ready');
              return e && e.dataset.route===route && e.dataset.run!==run;
            }""", arg=[route,previous], timeout=60000)
            if route == "Orders":
                page.get_by_test_id("stDataFrame").wait_for()
            transitions.append(dict(route=route, usableMs=round((time.perf_counter()-began)*1000,3)))
        if page.get_by_test_id("stException").count() or errors or external_requests:
            raise AssertionError(f"Fixture browser/network errors: {errors}; external requests: {external_requests}")
        return dict(cold=cold,reopened=reopened,transitions=transitions,errors=errors,
                    external_requests=external_requests)
    finally:
        context.close()


def run(args):
    from playwright.sync_api import sync_playwright
    result = dict(scope="Offline framework/transport fixture; not production Home/Orders end-to-end",
                  gzip_only=args.gzip_only, browser_channel=args.browser_channel,
                  simulated_auth_ms=40, simulated_data_miss_ms=120,
                  versions={name:importlib.metadata.version(name) for name in ["streamlit","starlette","uvicorn","playwright"]},
                  source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                    for name in ["app.py","sports_cave_server.py","supabase_backend.py","startup_performance.py",
                                 "static_asset_compression.py","public_bundle_cache.py","scripts/benchmark_app_startup.py",
                                 "scripts/startup_fixture_server.py","tests/fixtures/startup_measurement.py"]},
                  normal=[], slow=[], restarts=[])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="startup-fixture-", dir=args.out.parent) as directory:
        runtime = Path(directory)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel=args.browser_channel, args=[
                "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost",
                "--proxy-server=http://127.0.0.1:1", "--proxy-bypass-list=127.0.0.1;localhost"])
            try:
                with fixture_server(runtime) as (url, healthy, log):
                    result["initial_server_healthy_ms"] = healthy
                    for key, count in [("normal",args.samples),("slow",args.slow_samples)]:
                        for i in range(count):
                            print(f"{key} sample {i+1}/{count}", flush=True)
                            result[key].append(browser_sample(browser,url,slow=key=="slow",gzip_only=args.gzip_only))
                    result["server_log"] = log.read_text(encoding="utf-8")
                for i in range(args.restart_samples):
                    print(f"server restart {i+1}/{args.restart_samples}", flush=True)
                    with fixture_server(runtime) as (url, healthy, log):
                        sample = browser_sample(browser,url,gzip_only=args.gzip_only)
                        result["restarts"].append(dict(serverHealthyMs=healthy, firstBrowser=sample["cold"],
                            serverAndBrowserMs=round(healthy+sample["cold"]["usableMs"],3)))
            finally:
                browser.close()
    for name, original in result["source_sha256"].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != original:
            raise RuntimeError("Measured source changed during the benchmark; rerun against stable files.")
    result["summaries"] = {key:{
        "fresh_browser":summary([s["cold"]["usableMs"] for s in result[key]]),
        "cached_reopen":summary([s["reopened"]["usableMs"] for s in result[key]]),
        "warm_home":summary([t["usableMs"] for s in result[key] for t in s["transitions"] if t["route"]=="Home"]),
        "first_orders":summary([s["transitions"][0]["usableMs"] for s in result[key]]),
        "warm_orders":summary([s["transitions"][2]["usableMs"] for s in result[key]]),
    } for key in ["normal","slow"] if result[key]}
    args.out.write_text(json.dumps(result,indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result["summaries"],indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--slow-samples", type=int, default=3)
    parser.add_argument("--restart-samples", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--browser-channel", default=None)
    parser.add_argument("--gzip-only", action="store_true", help="Measure the previous transport on identical source")
    args = parser.parse_args()
    if args.samples < 1 or args.slow_samples < 0 or args.restart_samples < 0:
        parser.error("Use positive samples and non-negative slow/restart samples.")
    run(args)
