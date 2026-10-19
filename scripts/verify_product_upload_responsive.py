"""Focused actual Streamlit UI recovery/stale-output checks, loopback only."""
from pathlib import Path
import json,time
from playwright.sync_api import sync_playwright,expect


def main():
    base='http://127.0.0.1:8691'
    out=Path(__file__).resolve().parents[1]/'output/product-upload-responsive/verification';out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page(viewport=dict(width=1440,height=1100))
        page.goto(base);frame=page.frame_locator('iframe[src*="product_uploads_workflow"]')
        expect(frame.locator('#summary')).to_be_hidden(timeout=60000)
        page.request.post(base+'/__test/fail-next-preparation')
        def choose():
            frame.get_by_role('button',name='Choose PSD',exact=True).click()
            frame.get_by_role('button',name='the-eleventh-pitch-jake-bauers.psd',exact=True).click()
        choose();expect(frame.locator('#stage')).to_have_text('Error',timeout=20000)
        identity=frame.locator('body').evaluate('()=>window.productUploadMetrics.selections[0].id')
        # Retry retains this exact workflow and selected source, not a new product.
        frame.locator('#artwork-retry').click()
        generate=page.get_by_role('button',name='Generate mockups',exact=True)
        expect(generate).to_be_enabled(timeout=20000)
        after=frame.locator('body').evaluate('()=>window.productUploadMetrics.selections.filter(x=>x.id).at(-1).id')
        assert identity==after
        name=page.get_by_role('textbox',name='Product name',exact=True)
        name.fill('Retained product details');name.press('Tab');expect(name).to_have_value('Retained product details')
        generate.click()
        progress=page.get_by_text('Generating mockups · 1 of 5',exact=True)
        progress.wait_for(timeout=20000)
        expect(generate).to_be_disabled()
        click=time.monotonic();page.get_by_role('button',name='Responsiveness probe',exact=True).click()
        expect(page.get_by_text('Probe receipt: 1',exact=True)).to_be_visible(timeout=2000)
        interactive_ms=round((time.monotonic()-click)*1000,2)
        expect(name).to_have_value('Retained product details')
        page.wait_for_function("()=>[...document.querySelectorAll('img[alt=\"Completed mockup preview\"]')].some(image=>image.complete&&image.naturalWidth>0)")
        page.screenshot(path=str(out/'progress-and-responsive-form.png'),full_page=True)
        # Change selection while the first job still owns its old workflow.
        frame.get_by_role('button',name='Remove selected PSD',exact=True).click()
        expect(frame.locator('#summary')).to_be_hidden()
        choose();expect(generate).to_be_enabled(timeout=20000)
        page.wait_for_timeout(1500)
        assert not page.locator('.st-key-mockups-gallery img').count()
        expect(name).not_to_have_value('Retained product details')
        page.screenshot(path=str(out/'changed-selection-no-stale-results.png'),full_page=True)
        generate.click();expect(page.locator('.st-key-mockups-gallery img')).to_have_count(5,timeout=30000)
        page.screenshot(path=str(out/'complete-correct-mockups.png'),full_page=True)
        fresh=browser.new_page();fresh.goto(base)
        expect(fresh.frame_locator('iframe[src*="product_uploads_workflow"]').locator('#summary')).to_be_hidden(timeout=60000)
        assert not fresh.locator('.st-key-mockups-gallery img').count()
        metrics=page.request.get(base+'/__test/responsive-metrics').json();assert metrics['source_unchanged']
        report=dict(retry_kept_workflow=True,form_preserved=True,generate_disabled_while_running=True,
                    stale_results_discarded=True,fresh_page_empty=True,server_interaction_ms=interactive_ms,provider=metrics,
                    boundary='Actual Product Upload UI; affected PSD read-only; isolated provider failure injected; no external/Companion calls allowed.')
        (out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2));browser.close()


if __name__=='__main__':main()
