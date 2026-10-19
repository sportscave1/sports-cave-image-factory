"""Local Chrome regression check: preview-only gallery and explicit original actions."""
from pathlib import Path
import base64,io,json,urllib.request
from PIL import Image,ImageChops
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/product-upload-gallery-regression';OUT.mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:8692'
def main():
 with sync_playwright() as p:
  browser=p.chromium.launch(channel='chrome',headless=True)
  context=browser.new_context(viewport=dict(width=1440,height=1100),permissions=['clipboard-read','clipboard-write'])
  requests=[];errors=[]
  context.on('request',lambda r:requests.append(r.url) if '/api/product-uploads/asset?' in r.url else None)
  page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  before=page.request.get(BASE+'/__test/outputs').json()
  page.goto(BASE)
  picker=page.locator('iframe[src*="product_uploads_workflow"]').first.content_frame
  expect(picker.get_by_role('button',name='Choose PSD',exact=True)).to_be_visible(timeout=60000)
  picker.get_by_role('button',name='Choose PSD',exact=True).click()
  picker.get_by_role('button',name='the-eleventh-pitch-jake-bauers.psd',exact=True).click()
  generate=page.get_by_role('button',name='Generate mockups',exact=True)
  expect(generate).to_be_enabled(timeout=30000)
  page.evaluate("""()=>{window.previewSamples=[];window.previewWatch=new MutationObserver(()=>{const images=[...document.querySelectorAll('img[alt="Completed mockup preview"]')];if(images.length)window.previewSamples.push(images.map(i=>({src:i.src,width:i.getBoundingClientRect().width,top:i.getBoundingClientRect().top})));});window.previewWatch.observe(document.body,{childList:true,subtree:true});}""")
  generate.click()
  expect(page.get_by_text('Mockups ready',exact=True)).to_be_visible(timeout=30000)
  gallery=page.frame_locator('iframe[src*="product_upload_gallery"]').nth(0)
  actions=page.frame_locator('iframe[src*="product_upload_gallery"]').nth(1)
  expect(gallery.locator('.gallery img')).to_have_count(5)
  expect(actions.locator('#copyPrompt')).to_be_visible()
  assert requests==[],requests
  samples=page.evaluate('()=>{window.previewWatch.disconnect();return window.previewSamples}')
  assert samples and all(len(s)<=5 and all(i['src'].startswith('data:image/webp;base64,') and i['width']<=140 for i in s) for s in samples)
  assert all(len(set(i['top'] for i in sample))==1 for sample in samples)
  assert page.locator('img[alt="Completed mockup preview"]').count()==0
  page.locator('.st-key-product-upload-preview-row').scroll_into_view_if_needed()
  page.screenshot(path=str(OUT/'compact-gallery.png'))
  assert page.get_by_role('button',name='Edit master prompt',exact=True).count()==0
  assert page.locator('iframe[src*="product_upload_gallery"]').count()==2
  labels=gallery.locator('img').evaluate_all('(items)=>items.map(i=>i.alt)')
  assert labels==['Black Framed','Oak Framed','White Framed','Unframed','Size Guide'],labels
  previews=[]
  for img in gallery.locator('img').all():
   value=img.get_attribute('src');assert value.startswith('data:image/webp;base64,')
   data=base64.b64decode(value.split(',',1)[1])
   with Image.open(io.BytesIO(data)) as im:previews.append(dict(label=img.get_attribute('alt'),dimensions=im.size,bytes=len(data),format=im.format))
  boxes=gallery.locator('img').evaluate_all('(items)=>items.map(i=>{const b=i.getBoundingClientRect();return {top:b.top,width:b.width,height:b.height}})')
  assert len(set(b['top'] for b in boxes))==1 and all(b['height']<=110 for b in boxes),boxes
  page.get_by_role('button',name='Responsiveness probe',exact=True).click()
  expect(page.get_by_text('Probe receipt: 1',exact=True)).to_be_visible()
  expect(gallery.locator('img')).to_have_count(5)
  assert requests==[],requests
  # Open through keyboard only, recording the explicitly requested original response.
  original_url=gallery.locator('a').first.get_attribute('href')
  with context.expect_page() as popup:
   gallery.locator('a').first.focus();gallery.locator('a').first.press('Enter')
  tab=popup.value;tab.wait_for_load_state()
  expect(tab.locator('img')).to_be_visible()
  assert len(requests)==1 and requests[0]==original_url,requests
  dimensions=tab.locator('img').evaluate('(i)=>[i.naturalWidth,i.naturalHeight]')
  # Canvas reads the already opened original; it makes no new network request.
  original_pixels=tab.locator('img').evaluate('''i=>{const c=document.createElement('canvas');c.width=i.naturalWidth;c.height=i.naturalHeight;const x=c.getContext('2d');x.drawImage(i,0,0);return c.toDataURL('image/png').split(',')[1]}''')
  tab.close()
  actions.locator('#copyPrompt').click();expect(actions.locator('#copyPrompt')).to_have_text('Copied')
  master=page.evaluate('navigator.clipboard.readText()').replace('\r\n','\n')
  from product_upload_lifestyle import INSTRUCTIONS,PER_IMAGE
  assert master.startswith(INSTRUCTIONS) and master.count(PER_IMAGE)==3
  assert all(x in master for x in ('three genuinely different homes or properties','Immediately generate Card 1','No collage, triptych or contact sheet','original uploaded full-resolution framed product'))
  actions.locator('#copyImage').click();expect(actions.locator('#copyImage')).to_have_text('Copied',timeout=15000)
  copied=page.evaluate('''async()=>{const r=await navigator.clipboard.read();const b=await r[0].getType('image/png');return Array.from(new Uint8Array(await b.arrayBuffer()))}''')
  with Image.open(io.BytesIO(bytes(copied))) as image,Image.open(io.BytesIO(base64.b64decode(original_pixels))) as original:
   assert list(image.size)==dimensions
   assert ImageChops.difference(image.convert('RGBA'),original.convert('RGBA')).getbbox() is None
  assert requests==[original_url,original_url],requests
  # Real browser clipboard rejection: no successful-copy status or silent URL fallback.
  actions.locator('body').evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{write:()=>Promise.reject(new DOMException('denied','NotAllowedError')),writeText:()=>Promise.reject(new DOMException('denied','NotAllowedError'))}})")
  actions.locator('#copyImage').click();expect(actions.locator('#status')).to_contain_text('Could not copy image')
  expect(actions.locator('#status a')).to_be_visible()
  expect(actions.locator('#copyImage')).to_have_text('Copy black frame')
  actions.locator('#copyPrompt').click();expect(actions.locator('#status')).to_contain_text('Could not copy prompt')
  expect(actions.locator('#copyPrompt')).to_have_text('Copy prompt')
  for index,slot in enumerate(('01-man-cave-prompt','02-office-prompt','03-living-room-prompt')):
   path=OUT/(slot+'.png');Image.new('RGB',(2000,1200),[(70,90,120),(120,80,60),(60,120,80)][index]).save(path)
   page.locator('.st-key-mockups-lifestyle-'+slot+' input[type=file]').set_input_files(str(path))
   expect(page.get_by_text(f'{6+index} of 8 product images ready',exact=True)).to_be_visible(timeout=20000)
  assert page.locator('iframe[src*="product_upload_gallery"]').count()==5
  expect(gallery.locator('img')).to_have_count(5)
  count=len(requests)
  for slot in ('01-man-cave-prompt','02-office-prompt','03-living-room-prompt'):
   frame=page.locator('.st-key-mockups-lifestyle-'+slot+' iframe').content_frame
   with context.expect_page() as popup:frame.locator('a').click()
   tab=popup.value;tab.wait_for_load_state();expect(tab.locator('img')).to_be_visible()
   assert tab.locator('img').evaluate('(i)=>[i.naturalWidth,i.naturalHeight]')==[2000,1200]
   assert frame.locator('button').count()==0;tab.close()
  assert len(requests)==count+3
  count=len(requests)
  # All other previews are explicit user opens; each opens its own original only.
  for anchor in gallery.locator('a').all()[1:]:
   with context.expect_page() as popup:anchor.click()
   tab=popup.value;tab.wait_for_load_state();expect(tab.locator('img')).to_be_visible()
   assert tab.url==anchor.get_attribute('href');tab.close()
  assert len(requests)==count+4
  count=len(requests)
  page.get_by_role('button',name='Save all',exact=True).click()
  expect(page.get_by_role('button',name='folder Baseball',exact=True)).to_be_visible()
  expect(page.get_by_role('button',name='Save here',exact=True)).to_be_disabled()
  page.get_by_role('button',name='folder Baseball',exact=True).click()
  page.get_by_role('button',name='Save here',exact=True).click()
  expect(page.get_by_text('Saved to Dropbox',exact=True)).to_be_visible(timeout=30000)
  calls=page.request.get(BASE+'/__test/outputs').json()['calls'][len(before['calls']):]
  assert len([c for c in calls if c[0]=='upload'])==16,calls
  assert all('/Baseball/the-eleventh-pitch-jake-bauers' in c[1] for c in calls if c[0]=='upload')
  assert len(requests)==count
  page.screenshot(path=str(OUT/'ui.png'),full_page=True)
  picker.get_by_role('button',name='Remove selected PSD',exact=True).click()
  expect(picker.locator('#summary')).to_be_hidden()
  expect(page.get_by_text('Mockups ready',exact=True)).to_have_count(0)
  assert page.locator('iframe[src*="product_upload_gallery"]').count()==0
  assert page.request.get(original_url).status!=200
  report=dict(browser='installed desktop Chrome, headless',previews=previews,one_horizontal_row=True,during_generation_preview_only_one_row=True,
   preview_only_initial_and_rerender=True,each_explicit_open_correct=True,original_dimensions=dimensions,
   clipboard_original_dimensions_and_pixels_match=True,complete_resolved_prompt=True,clipboard_denial_honest=True,
   three_lifestyle_uploads=True,save_16_original_outputs_mocked=True,save_no_browser_original_requests=True,
   stale_actions_removed_and_original_revoked=True,js_errors=errors,
   boundary='Loopback fixture; affected PSD read-only, synthetic lifestyle uploads, mocked Dropbox writes; companion prohibited. No external ChatGPT generation, OS paste or production UI claim.')
  (OUT/'ui-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2));browser.close()
if __name__=='__main__':main()
