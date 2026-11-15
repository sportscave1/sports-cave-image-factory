"""Focused loopback UI/copy/save checks; never opens external ChatGPT or Dropbox."""
from pathlib import Path
import json
import io
import hashlib
import re
from PIL import Image,ImageChops
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/product-upload-lifestyle';OUT.mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:8692'


def main():
    with sync_playwright() as p:
        try:browser=p.chromium.launch(channel='chrome',headless=True);channel='installed Chrome (headless)'
        except Exception:browser=p.chromium.launch(headless=True);channel='bundled Chromium (headless)'
        context=browser.new_context(viewport=dict(width=1440,height=1100),permissions=['clipboard-read','clipboard-write'])
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        import urllib.request
        before=json.loads(urllib.request.urlopen(BASE+'/__test/outputs').read())
        page.goto(BASE)
        picker=page.locator('iframe[src*="product_uploads_workflow"]').first.content_frame
        expect(picker.get_by_role('button',name='Choose PSD',exact=True)).to_be_visible(timeout=60000)
        picker.get_by_role('button',name='Choose PSD',exact=True).click()
        picker.get_by_role('button',name='the-eleventh-pitch-jake-bauers.psd',exact=True).click()
        generate=page.get_by_role('button',name='Generate mockups',exact=True)
        expect(generate).to_be_enabled(timeout=30000);generate.click()
        expect(page.get_by_text('Mockups ready',exact=True)).to_be_visible(timeout=30000)
        assert page.get_by_text('Load Full Resolution',exact=True).count()==0
        assert page.get_by_text('Download ZIP',exact=True).count()==0
        assert page.get_by_text('Export mockups.',exact=True).count()==0
        assert page.get_by_text('8 JPG files ready for socials.',exact=True).count()==0
        expect(page.get_by_text('Man Cave',exact=True)).to_be_visible()
        expect(page.get_by_text('Office',exact=True)).to_be_visible()
        expect(page.get_by_text('Living Room',exact=True)).to_be_visible()
        def gallery_frames():return [f for f in page.frames if f.locator('#copyImage').count() or f.locator('#copyPrompt').count() or f.locator('small').filter(has_text='Preview shown').count()]
        frames=gallery_frames();assert len(frames)==6,len(frames)
        row=next(f for f in frames if f.locator('#copyPrompt').count())
        expect(row.get_by_role('button',name='Copy black frame',exact=True)).to_be_enabled()
        row.get_by_role('button',name='Copy prompt',exact=True).click()
        expect(row.locator('#copyPrompt')).to_have_text('Copied')
        master=page.evaluate('navigator.clipboard.readText()').replace('\r\n','\n')
        from product_upload_lifestyle import INSTRUCTIONS,PER_IMAGE,READ_FIRST,FINAL_CHECK
        assert master.startswith(READ_FIRST) and master.endswith(FINAL_CHECK) and INSTRUCTIONS in master and master.count(PER_IMAGE)==3
        assert all(x in master for x in ('three genuinely different homes or properties','Immediately generate Card 1','No collage, triptych or contact sheet','original uploaded full-resolution framed product'))
        (OUT/'master-prompt.txt').write_text(master,encoding='utf-8')
        original_url=row.evaluate('original')
        original=page.request.get(original_url)
        assert original.status==200,(original.status,original.text()[:300])
        with Image.open(io.BytesIO(original.body())) as image:
            original_dimensions=image.size;original_pixels=image.convert('RGB').copy()
        row.get_by_role('button',name='Copy black frame',exact=True).click()
        expect(row.locator('#copyImage')).to_have_text('Copied',timeout=15000)
        copied=page.evaluate('''async()=>{const rows=await navigator.clipboard.read();const blob=await rows[0].getType('image/png');return Array.from(new Uint8Array(await blob.arrayBuffer()));}''')
        with Image.open(io.BytesIO(bytes(copied))) as image:
            assert image.size==original_dimensions
            with ImageChops.difference(original_pixels,image.convert('RGB')) as diff:assert diff.getbbox() is None
        # Keyboard activation opens the actual original, never the thumbnail.
        black=next(f for f in frames if f.locator('img[alt="Black Framed"]').count())
        assert black.locator('#copyImage').count()==0
        with page.expect_popup() as popup:
            black.locator('a').focus();black.locator('a').press('Enter')
        opened=popup.value;opened.wait_for_load_state()
        assert opened.url==original_url
        dimensions=opened.locator('img').evaluate('(i)=>[i.naturalWidth,i.naturalHeight]')
        assert tuple(dimensions)==original_dimensions
        opened.close()
        # Denied clipboard must report failure, never a successful copy.
        white=next(f for f in frames if f.locator('img[alt="White Framed"]').count())
        white.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{write:()=>Promise.reject(new DOMException('denied','NotAllowedError'))}})")
        white.locator('#copyImage').click();expect(white.locator('#status')).to_contain_text('Could not copy image')
        expect(white.get_by_role('link',name='Open original')).to_be_visible()
        # Upload three distinct real images through the unchanged slot lifecycle.
        for index,label in enumerate(('Man Cave','Office','Living Room')):
            path=OUT/(label.replace(' ','-')+'.png');Image.new('RGB',(2000,1200),[(70,90,120),(120,80,60),(60,120,80)][index]).save(path)
            page.locator('.st-key-mockups-lifestyle-'+('01-man-cave-prompt' if index==0 else '02-office-prompt' if index==1 else '03-living-room-prompt')).locator('input[type=file]').set_input_files(str(path))
            expect(page.get_by_text(f'{6+index} of 8 product images ready',exact=True)).to_be_visible(timeout=20000)
        lifestyle=page.locator('.st-key-mockups-lifestyle-01-man-cave-prompt iframe').content_frame
        expect(lifestyle.locator('img')).to_be_visible()
        lifestyle_url=lifestyle.locator('body').evaluate('()=>original')
        assert page.request.get(lifestyle_url).body()==(OUT/'Man-Cave.png').read_bytes()
        lifestyle.locator('#copyImage').click();expect(lifestyle.locator('#copyImage')).to_have_text('Copied')
        copied_lifestyle=page.evaluate('''async()=>{const rows=await navigator.clipboard.read();const blob=await rows[0].getType('image/png');return Array.from(new Uint8Array(await blob.arrayBuffer()));}''')
        with Image.open(io.BytesIO(bytes(copied_lifestyle))) as image:assert image.size==(2000,1200)
        all_originals=[]
        for f in gallery_frames():
            if not f.locator('img').count():continue
            url=f.locator('body').evaluate('()=>original')
            assert url not in all_originals;all_originals.append(url)
            with page.expect_popup() as popup:f.locator('a').first.click()
            tab=popup.value;tab.wait_for_load_state()
            assert tab.url==url
            expect(tab.locator('img')).to_be_visible();tab.close()
        assert len(all_originals)==8
        page.get_by_role('button',name='Save all',exact=True).click()
        collection=page.get_by_role('button',name='folder Baseball',exact=True)
        expect(collection).to_be_visible()
        expect(page.get_by_role('button',name='Save here',exact=True)).to_be_disabled()
        collection.click()
        expect(page.get_by_role('button',name='Save here',exact=True)).to_be_enabled()
        page.request.post(BASE+'/__test/fail-save?name=*')
        page.get_by_role('button',name='Save here',exact=True).click()
        expect(page.get_by_role('progressbar')).to_be_visible(timeout=10000)
        expect(page.get_by_role('button',name='Generate mockups',exact=True)).to_be_disabled()
        expect(page.get_by_role('button',name='Save all',exact=True)).to_be_disabled()
        page.get_by_role('button',name='Responsiveness probe',exact=True).click()
        expect(page.get_by_text('Probe receipt: 1',exact=True)).to_be_visible()
        expect(page.get_by_text('Save incomplete.',exact=False)).to_be_visible(timeout=30000)
        page.get_by_role('button',name='Save all',exact=True).click()
        expect(page.get_by_role('button',name='Save here',exact=True)).to_be_disabled()
        expect(collection).to_be_visible();collection.click()
        expect(page.get_by_role('button',name='Save here',exact=True)).to_be_enabled()
        page.get_by_role('button',name='Save here',exact=True).click()
        expect(page.get_by_text('Saved to Dropbox',exact=True)).to_be_visible(timeout=30000)
        expect(page.get_by_role('link',name='Open folder',exact=True)).to_be_visible()
        metrics=page.request.get(BASE+'/__test/outputs').json()
        calls=metrics['calls'][len(before['calls']):]
        assert len([c for c in calls if c[0]=='upload'])==17,calls
        assert len([c for c in calls if c[0]=='folder'])==1,calls
        assert all('/Baseball/the-eleventh-pitch-jake-bauers' in c[1] for c in calls if c[0]=='upload')
        page.screenshot(path=str(OUT/'ui.png'),full_page=True)
        # Old original URLs are revoked on source change, including cached iframe actions.
        picker.get_by_role('button',name='Remove selected PSD',exact=True).click()
        expect(picker.locator('#summary')).to_be_hidden()
        expect(page.get_by_text('Mockups ready',exact=True)).to_have_count(0)
        assert page.request.get(original_url).status!=200
        fresh=context.new_page();fresh.goto(BASE)
        expect(fresh.frame_locator('iframe[src*="product_uploads_workflow"]').locator('#summary')).to_be_hidden(timeout=30000)
        report=dict(browser=channel,one_master_prompt=True,three_upload_slots=True,original_dimensions=original_dimensions,
            clipboard_png_dimensions_and_pixels_match=True,original_open_keyboard=True,clipboard_denial_honest=True,
            uploaded_original_dimensions=[2000,1200],uploaded_original_bytes_preserved=True,
            every_preview_opens_correct_original=True,save_progress_visible=True,form_responsive_during_save=True,
            save_root_and_sport_selection=True,partial_retry_same_folder_skips_confirmed=True,save_originals=16,
            stale_original_revoked=True,fresh_empty=True,
            js_errors=errors,boundary='Loopback app; original PSD read-only, synthetic lifestyle images, mocked Dropbox writes, companion prohibited. No external ChatGPT generation, visual A1 accuracy or OS paste verification.')
        (OUT/'ui-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2));browser.close()


if __name__=='__main__':main()
