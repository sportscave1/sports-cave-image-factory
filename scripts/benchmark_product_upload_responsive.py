"""Actual loopback Streamlit UI timing; no live server or provider writes."""
import argparse,json,time
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8691');parser.add_argument('--label',default='before');parser.add_argument('--exercise',action='store_true');args=parser.parse_args()
    assert args.url.startswith('http://127.0.0.1:')
    out=Path(__file__).resolve().parents[1]/'output/product-upload-responsive'/args.label;out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page(viewport=dict(width=1440,height=1100))
        page.goto(args.url)
        frame=page.frame_locator('iframe[src*="product_uploads_workflow"]')
        frame.get_by_role('button',name='Choose PSD',exact=True).wait_for(timeout=60000)
        samples=[];probe_count=0
        for kind in ('cold','cached'):
            if kind=='cached':frame.get_by_role('button',name='Remove selected PSD').click()
            frame.get_by_role('button',name='Choose PSD',exact=True).click()
            selected=frame.get_by_role('button',name='the-eleventh-pitch-jake-bauers.psd',exact=True)
            selected.wait_for();started=time.monotonic();selected.click()
            generate=page.get_by_role('button',name='Generate Core Shopify Images' if args.label=='before' else 'Generate mockups',exact=True)
            generate.wait_for(timeout=60000)
            preparation_stages=[];captured=False
            while not generate.is_enabled():
                stage=frame.locator('#stage').inner_text()
                if not preparation_stages or preparation_stages[-1]!=stage:preparation_stages.append(stage)
                if args.exercise and 'Downloading PSD' in stage and not captured and float(frame.locator('#progress').get_attribute('value') or 0)>40:
                    page.screenshot(path=str(out/(kind+'-downloading.png')),full_page=True);captured=True
                if time.monotonic()-started>90:raise RuntimeError('Artwork never became ready')
                page.wait_for_timeout(50)
            ready=time.monotonic();page.screenshot(path=str(out/(kind+'-ready.png')),full_page=True)
            clicked=time.monotonic();generate.click()
            feedback=None;counts=[];probe_started=None;probe_ms=None;generation_screen=False
            while page.locator('.st-key-mockups-gallery img').count()!=5 or not page.locator('.st-key-mockups-gallery img').evaluate_all('(images)=>images.every(image=>image.complete&&image.naturalWidth>0)'):
                if feedback is None and (page.get_by_text('Generating',exact=False).count() or page.get_by_text('Waiting for renderer',exact=False).count()):feedback=time.monotonic()
                text=page.locator('body').inner_text()
                import re
                for count in re.findall(r'Generating mockups · (\d) of 5',text):
                    if count not in counts:counts.append(count)
                if args.exercise and args.label!='before' and '2' in counts and not generation_screen:
                    page.screenshot(path=str(out/(kind+'-generating.png')),full_page=True);generation_screen=True
                if args.exercise and args.label!='before' and probe_started is None and '1' in counts:
                    probe_started=time.monotonic();page.get_by_role('button',name='Responsiveness probe',exact=True).click();probe_count+=1
                if probe_started is not None and probe_ms is None and f'Probe receipt: {probe_count}' in text:probe_ms=round((time.monotonic()-probe_started)*1000,2)
                if time.monotonic()-clicked>90:
                    (out/'failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8');raise RuntimeError('Mockups never displayed')
                page.wait_for_timeout(50)
            completed=time.monotonic()
            events=frame.locator('body').evaluate('()=>window.productUploadMetrics.selections')
            identity=next((event['id'] for event in reversed(events) if event.get('id')),None)
            state=page.request.get(args.url+'/api/product-uploads/state?id='+identity).json()['upload'] if identity else {}
            previews=[event['selection_to_preview_ms'] for event in events if event.get('id')==identity and 'selection_to_preview_ms' in event]
            samples.append(dict(kind=kind,selection_to_first_preview_ms=min(previews) if previews else None,selection_to_ready_ms=round((ready-started)*1000,2),click_to_first_feedback_ms=round((feedback-clicked)*1000,2) if feedback else None,click_to_all_mockups_ms=round((completed-clicked)*1000,2),preparation_stages=preparation_stages,completed_image_counts=counts,server_probe_during_generation_ms=probe_ms,server_preparation=state.get('artwork_progress')))
            page.screenshot(path=str(out/(kind+'-generated.png')),full_page=True)
        metrics=page.request.get(args.url+'/__test/responsive-metrics').json()
        evidence=dict(samples=samples,provider=metrics,boundary='Actual Product Upload Streamlit/component/shared image engine; affected original read-only, disposable SQL and isolated Dropbox stream limited to32MiB/s. Local timings, not Render performance.')
        (out/'browser-timings.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence,indent=2));browser.close()


if __name__=='__main__':main()
