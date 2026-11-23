"""Real MV3 extension, five synthetic tabs, bounded offline soak; no paired device."""
import json
from pathlib import Path
import tempfile
import time
from playwright.sync_api import sync_playwright


def run():
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as profile, sync_playwright() as p:
        extension=str(root/'windows-upload-companion')
        context=p.chromium.launch_persistent_context(profile,channel='chromium',headless=True,
            args=['--disable-extensions-except='+extension,'--load-extension='+extension])
        try:
            worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
            version=worker.evaluate('chrome.runtime.getManifest().version')
            assert version=='1.7.21'
            context.route('**/*',lambda route:route.fulfill(body='<main><div data-message-author-role="assistant">Synthetic work in progress</div></main>',content_type='text/html'))
            pages=[]
            for i in range(5):
                page=context.new_page()
                page.goto('https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/c/00000000-0000-0000-0000-00000000000'+str(i))
                pages.append(page)
            def reads():
                return worker.evaluate('''async()=>{
                    const tabs=await chrome.tabs.query({url:'https://chatgpt.com/*'});
                    return await Promise.all(tabs.map(tab=>chrome.tabs.sendMessage(tab.id,{type:'project:progress'})));
                }''')
            # Extension document_idle can follow the navigation completion.
            for attempt in range(30):
                try:
                    first=reads();break
                except Exception:
                    if attempt==29:raise
                    pages[0].wait_for_timeout(100)
            assert len(first)==5 and all(not x['blocked'] for x in first)
            def heap():
                values=[]
                for page in pages:
                    c=context.new_cdp_session(page);c.send('HeapProfiler.collectGarbage');c.send('Performance.enable')
                    values.append({m['name']:m['value'] for m in c.send('Performance.getMetrics')['metrics']}['JSHeapUsedSize']);c.detach()
                return values
            before=heap();count=0;started=time.monotonic()
            while time.monotonic()-started<60:
                assert reads()==first
                count+=5;pages[0].wait_for_timeout(200)
            after=heap()
            assert sum(after)<sum(before)+5_000_000
            pages[0].evaluate("document.querySelector('[data-message-author-role]').textContent='SC_DESIGN_BLOCKED: Synthetic missing PSD'")
            changed=reads();assert sum(x['blocked'] for x in changed)==1
            assert not worker.evaluate("async()=>Boolean((await chrome.storage.local.get('staffQueueCredential')).staffQueueCredential)")
            return dict(version=version,tabs=5,seconds=round(time.monotonic()-started,2),observations=count,
                heap_before=before,heap_after=after,changed_blocker_detected=True,paired=False)
        finally:context.close()


if __name__=='__main__':print(json.dumps(run(),indent=2))
