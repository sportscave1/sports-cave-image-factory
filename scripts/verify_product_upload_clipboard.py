"""Offline Chromium QA against tests.fixtures.product_upload_package_ui only."""
import base64
import json
from pathlib import Path
import sys
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

base=sys.argv[1]
assert urlparse(base).hostname in ('127.0.0.1','localhost'), 'Synthetic loopback fixture required'
root=Path(__file__).resolve().parents[1]
out=root/'output/product-upload-clipboard';out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    context=browser.new_context(permissions=['clipboard-read','clipboard-write'],viewport={'width':1280,'height':900})
    page=context.new_page();requests=[];errors=[]
    page.on('request',lambda r:requests.append(r.url))
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/component')
    cards=page.locator('.saved-card');expect(cards).to_have_count(8)
    page.wait_for_function("[...document.querySelectorAll('.saved-card img')].every(i=>i.complete&&i.naturalWidth>0)")
    assert not any('saved-image?' in u and 'thumbnail=1' not in u for u in requests)
    assert not any('clipboard-' in u or 'files-native' in u for u in requests)
    dimensions=[]
    for i in range(8):
        card=cards.nth(i);button=card.get_by_role('button')
        original=card.locator('a').get_attribute('href')
        assert 'thumbnail' not in original and 'version=' in original and 'role=' in original
        before=len([u for u in requests if 'saved-image?' in u and 'thumbnail=1' not in u])
        button.click();expect(button).to_have_text('Copied ✓')
        assert len([u for u in requests if 'saved-image?' in u and 'thumbnail=1' not in u])==before+1
        source=context.request.get(base+original).body()
        result=page.evaluate("""async encoded=>{
            const entries=await navigator.clipboard.read();const entry=entries[0];
            const blob=await entry.getType(entry.types.includes('image/webp')?'image/webp':'image/png');
            const original=new Blob([Uint8Array.from(atob(encoded),c=>c.charCodeAt(0))],{type:'image/webp'});
            async function pixels(b){const image=await createImageBitmap(b);const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;canvas.getContext('2d').drawImage(image,0,0);const bytes=canvas.getContext('2d').getImageData(0,0,image.width,image.height).data;const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).join(',');return {width:image.width,height:image.height,digest};}
            return {format:blob.type,actual:await pixels(blob),expected:await pixels(original)};
        }""",base64.b64encode(source).decode())
        assert result['actual']==result['expected'],result
        assert result['actual']['width']==1024 and result['actual']['height']==1024
        assert card.locator('img').evaluate('(i)=>i.naturalWidth')==128
        dimensions.append({'role':card.locator('span').inner_text(),'width':1024,'height':1024,'clipboard':result['format'],'pixels_match':True})
    button=cards.nth(0).get_by_role('button');button.click();expect(button).to_have_text('Copied ✓')
    before=len(requests);button.click();expect(button).to_have_text('Copied ✓');assert len(requests)==before
    page.wait_for_timeout(2100);expect(button).to_have_text('Copy')
    for mode in ('DRAFT','LIVE','UPDATE'):
        page.locator('#mode').select_option(mode)
        page.wait_for_timeout(50)
        page.locator('#copy').click();expect(page.locator('#copy')).to_have_text('Copied ✓')
        text=page.evaluate('navigator.clipboard.readText()')
        row=context.request.get(base+'/api/product-uploads/state').json()['upload']
        expected=context.request.post(base+'/api/product-uploads/prompt',data={'id':row['id'],'mode':mode}).json()['prompt']
        assert text.replace('\r\n','\n')==expected.replace('\r\n','\n')
        assert 'Fixture '+mode+' prompt for Fixture artwork.psd' in text
        assert page.locator('dialog[open]').count()==0
        assert page.url==base+'/component'
    page.wait_for_timeout(2100);expect(page.locator('#copy')).to_have_text('Copy upload prompt')
    page.evaluate("() => {navigator.clipboard.write=async()=>{throw new DOMException('Denied','NotAllowedError')}}")
    page.locator('#copy').click();expect(page.locator('#error')).to_contain_text('Could not copy prompt')
    assert page.locator('dialog[open]').count()==0
    assert not page.locator('textarea').count()
    cards.nth(1).get_by_role('button').click();expect(cards.nth(1).locator('.saved-copy-status')).to_contain_text('Allow clipboard')
    for width in (1280,390):
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        for card in cards.all():
            bounds=card.evaluate("c=>{const a=c.querySelector('a').getBoundingClientRect(),b=c.querySelector('button').getBoundingClientRect();return {imageBottom:a.bottom,buttonTop:b.top}}")
            assert bounds['buttonTop']>=bounds['imageBottom']
        page.screenshot(path=str(out/f'gallery-{width}.png'),full_page=True)
    # Exercise the same-origin iframe and record activation at the API call.
    iframe_context=browser.new_context(permissions=['clipboard-read','clipboard-write'])
    iframe_context.add_init_script("const write=navigator.clipboard.write.bind(navigator.clipboard);navigator.clipboard.write=items=>{window.clipboardClickActive=navigator.userActivation.isActive;return write(items)}")
    shell=iframe_context.new_page();shell.goto(base+'/')
    embedded=shell.frame_locator('#component')
    expect(embedded.locator('.saved-card')).to_have_count(8)
    first=embedded.locator('.saved-card').first.get_by_role('button')
    first.click();expect(first).to_have_text('Copied ✓')
    embedded.locator('#copy').click();expect(embedded.locator('#copy')).to_have_text('Copied ✓')
    assert shell.frames[1].evaluate('window.clipboardClickActive') is True
    iframe_context.close()
    assert not any('clipboard-' in u or 'files-native' in u for u in requests)
    assert not errors,errors
    result={'images':dimensions,'prompt_modes':['DRAFT','LIVE','UPDATE'],'prompt_modal':False,'companion_requests':0,'browser_errors':errors,'ChatGPT_paste':'Not exercised; synthetic local fixture only'}
    (out/'results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    browser.close()
