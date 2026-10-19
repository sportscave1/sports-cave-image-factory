"""Installed Windows Chrome/Edge QA against the synthetic loopback package fixture."""
import hashlib
import json
from io import BytesIO
from pathlib import Path
import sys
from urllib.parse import urlparse
from PIL import Image
from playwright.sync_api import sync_playwright, expect

base=sys.argv[1];channel=sys.argv[2] if len(sys.argv)>2 else 'chrome'
assert urlparse(base).hostname in ('127.0.0.1','localhost'), 'Synthetic loopback fixture required'
assert channel in ('chrome','msedge')
root=Path(__file__).resolve().parents[1]
out=root/'output/product-webp-exact'/channel;out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(channel=channel,headless=True)
    context=browser.new_context(permissions=['clipboard-read','clipboard-write'],viewport={'width':1280,'height':900})
    page=context.new_page();requests=[];errors=[];downloads=[]
    page.on('request',lambda r:requests.append(r.url));page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('download',lambda d:downloads.append(d.suggested_filename))
    page.goto(base+'/component');cards=page.locator('.saved-card');expect(cards).to_have_count(8)
    page.wait_for_function("[...document.querySelectorAll('.saved-card img')].every(i=>i.complete&&i.naturalWidth>0)")
    assert not any('saved-image?' in u and 'thumbnail=1' not in u for u in requests)
    row=context.request.get(base+'/api/product-uploads/state').json()['upload']
    assert page.locator('#mode').input_value()==row['mode'], 'Saved upload mode must be retained'
    saved=context.request.get(base+'/api/product-uploads/saved-package?id='+row['id']).json()
    results=[]
    for i,item in enumerate(saved['items']):
        card=cards.nth(i);expect(card.locator('.saved-copy')).to_be_disabled()
        expect(card.locator('.saved-copy')).to_have_text('Copy unavailable')
        assert card.locator('a').get_attribute('href')==item['original']
        assert 'thumbnail' not in item['download'] and 'download=1' in item['download']
        before=len([u for u in requests if 'download=1' in u])
        with page.expect_download() as event:card.locator('.saved-download').click()
        download=event.value
        expect(card.locator('.saved-download')).to_have_text('Download started')
        assert download.suggested_filename==item['name']
        assert len([u for u in requests if 'download=1' in u])==before+1
        downloaded=Path(download.path()).read_bytes()
        response=context.request.get(base+item['original']);original=response.body()
        assert response.headers['content-type']=='image/webp'
        assert downloaded==original and len(original)==item['size']
        assert original[:4]==b'RIFF' and original[8:12]==b'WEBP'
        assert hashlib.sha256(hashlib.sha256(original).digest()).hexdigest()==item['content_hash']
        image=Image.open(BytesIO(downloaded));assert image.format=='WEBP' and image.size==(1024,1024)
        assert card.locator('img').evaluate('(i)=>i.naturalWidth')==128
        download.save_as(out/item['name'])
        results.append(dict(role=item['role'],filename=download.suggested_filename,mime='image/webp',sha256=hashlib.sha256(downloaded).hexdigest(),receipt_hash_match=True))
    before=len(requests)
    with page.expect_download():cards.nth(0).locator('.saved-download').click()
    assert len(requests)==before,'cached validated original should be reused'
    page.wait_for_timeout(2100);expect(cards.nth(0).locator('.saved-download')).to_have_text('Download WEBP')
    for mode in ('DRAFT','LIVE','UPDATE'):
        page.locator('#mode').select_option(mode);page.wait_for_timeout(50)
        page.locator('#copy').click();expect(page.locator('#copy')).to_have_text('Copied ✓')
        text=page.evaluate('navigator.clipboard.readText()')
        expected=context.request.post(base+'/api/product-uploads/prompt',data={'id':row['id'],'mode':mode}).json()['prompt']
        assert text.replace('\r\n','\n')==expected.replace('\r\n','\n')
        assert page.locator('dialog[open]').count()==0 and page.url==base+'/component'
    page.wait_for_timeout(2100);expect(page.locator('#copy')).to_have_text('Copy upload prompt')
    page.evaluate("() => {navigator.clipboard.write=async()=>{throw new DOMException('Denied','NotAllowedError')}}")
    page.locator('#copy').click();expect(page.locator('#error')).to_contain_text('Could not copy prompt')
    assert not page.locator('textarea').count() and page.locator('dialog[open]').count()==0
    for width in (1280,390):
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        for card in cards.all():
            bounds=card.evaluate("c=>{const a=c.querySelector('a').getBoundingClientRect(),buttons=[...c.querySelectorAll('button')].map(b=>b.getBoundingClientRect());return {imageBottom:a.bottom,copyTop:buttons[0].top,copyBottom:buttons[0].bottom,downloadTop:buttons[1].top}}")
            assert bounds['copyTop']>=bounds['imageBottom'] and bounds['downloadTop']>=bounds['copyBottom']
        page.screenshot(path=str(out/f'gallery-{width}.png'),full_page=True)
    # A changed valid-size source must fail byte verification and never download.
    def corrupt(route):
        response=route.fetch();data=bytearray(response.body());data[-1]^=1
        route.fulfill(response=response,body=bytes(data))
    page.route('**/api/product-uploads/saved-image?*download=1',corrupt)
    page.reload();expect(cards).to_have_count(8);before=len(downloads)
    cards.nth(0).locator('.saved-download').click()
    expect(cards.nth(0).locator('.saved-copy-status')).to_contain_text('bytes differ')
    assert len(downloads)==before
    # Same-origin embedded gallery also delivers the original named file.
    page.unroute('**/api/product-uploads/saved-image?*download=1')
    shell=context.new_page();shell.goto(base+'/');embedded=shell.frame_locator('#component')
    expect(embedded.locator('.saved-card')).to_have_count(8)
    with shell.expect_download() as event:embedded.locator('.saved-card').first.locator('.saved-download').click()
    assert event.value.suggested_filename==saved['items'][0]['name']
    assert not any('clipboard-' in u or 'files-native' in u for u in requests)
    assert not errors,errors
    result={'channel':channel,'version':browser.version,'files':results,'companion_requests':0,'prompt_modes':['DRAFT','LIVE','UPDATE'],'tampered_source_rejected':True,'ChatGPT_paste':'Unverified; browser-only exact file copying disabled'}
    (out/'results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    browser.close()
