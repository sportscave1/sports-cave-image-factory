"""Real Chromium clipboard and Streamlit component-route regression checks."""
import os, subprocess, sys, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
env={k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','COMSPEC','PATHEXT','LOCALAPPDATA','APPDATA','PROGRAMFILES','PROGRAMFILES(X86)')}
log=open(ROOT/'output-copy-preview.log','w')
server=subprocess.Popen([sys.executable,'-m','streamlit','run',str(ROOT/'scripts/product_upload_copy_preview.py'),'--server.port=8793','--server.address=127.0.0.1'],cwd=ROOT,env=env,stdout=log,stderr=log)
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(channel='msedge',headless=True)
  context=browser.new_context(permissions=['clipboard-read','clipboard-write'])
  page=context.new_page();errors=[];assets=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('response',lambda r:assets.append((r.url,r.status)) if '/component/' in r.url else None)
  for attempt in range(30):
   try:page.goto('http://127.0.0.1:8793');break
   except Exception:time.sleep(.3)
  save=page.get_by_role('button',name='Save all',exact=True)
  save.click()
  saved=page.get_by_text('\u2713 Saved',exact=True);expect(saved).to_be_visible()
  frame=page.frame_locator('iframe[title="product_upload_prompt_copy.product_upload_prompt_copy"]')
  copy=frame.locator('#copy');expect(copy).to_be_enabled()
  paste=page.get_by_role('textbox',name='Paste verification')
  def copied_text():
   copy.click();expect(copy).to_have_text('Copied \u2713')
   paste.fill('');paste.click();paste.press('Control+V');return paste.input_value()
  first=copied_text()
  assert 'COMPLETION CHECK AND RETURN TO MAP' in first and 'Synthetic product.psd' in first and 'product (2)/WEBP' in first
  save.click();expect(copy).to_have_text('Copy Upload Prompt');assert copied_text()!=first
  f=next(f for f in page.frames if 'product_upload_prompt_copy' in f.url)
  f.evaluate("() => {window.originalWrite=navigator.clipboard.writeText.bind(navigator.clipboard);navigator.clipboard.writeText=()=>Promise.reject(new Error('denied'));}")
  copy.click();expect(frame.get_by_role('status')).to_contain_text('Allow clipboard access');expect(saved).to_be_visible();expect(copy).to_be_enabled()
  f.evaluate('() => {navigator.clipboard.writeText=window.originalWrite;}');copied_text()
  page.get_by_role('button',name='Switch product').click();expect(page.locator('iframe[title="product_upload_prompt_copy.product_upload_prompt_copy"]')).to_have_count(0)
  save.click();text=copied_text();assert 'Other product.psd' in text and 'Synthetic product.psd' not in text
  f=next(f for f in page.frames if 'product_upload_prompt_copy' in f.url)
  f.evaluate("() => {window.originalWrite=navigator.clipboard.writeText.bind(navigator.clipboard);navigator.clipboard.writeText=()=>new Promise(resolve=>window.finishOldCopy=resolve);}")
  copy.click();save.click();expect(copy).to_have_text('Copy Upload Prompt');expect(copy).to_be_enabled()
  f.evaluate("() => {window.finishOldCopy();navigator.clipboard.writeText=window.originalWrite;}")
  expect(copy).to_have_text('Copy Upload Prompt')
  blocked='**/component/product_upload_prompt_copy.product_upload_prompt_copy/**'
  context.route(blocked,lambda route:route.abort())
  page.get_by_role('button',name='Retry copy controls').click();expect(saved).to_be_visible()
  context.unroute(blocked)
  page.get_by_role('button',name='Retry copy controls').click();expect(copy).to_be_enabled()
  page.get_by_text('Mount workflow assets',exact=True).click()
  wf=page.frame_locator('iframe[title$=".product_uploads_workflow"]')
  expect(wf.locator('#error')).to_be_visible() # API absent, but ready/render handshake succeeds.
  for name in ('mapping.js','app.js'):
   assert any(u.endswith('/'+name) and s==200 for u,s in assets),assets
  assert not errors,errors
  print(json.dumps({'save_copy_paste':True,'repeat_save':True,'switch_product':True,'clipboard_denial_retry':True,'late_completion_ignored':True,'asset_retry':True,'production_component_assets':assets,'console_errors':errors,'prompt_length':len(first)},indent=2))
  # Reproduce the old bootstrap failure when its authenticated script routes fail.
  baseline=context.new_page()
  baseline.add_init_script("window.readyMessages=[];window.addEventListener('message',e=>{if(e.data?.type==='streamlit:componentReady')window.readyMessages.push(e.data);});")
  old_html=(ROOT/'components/product_uploads/index.html').read_text(encoding='utf-8').replace('./mapping.js','/product-upload-mapping.js').replace('./app.js','/product-uploads.js')
  context.route('**/component/*.product_uploads_workflow/index.html?*',lambda route:route.fulfill(status=200,content_type='text/html',body=old_html))
  context.route('**/product-upload-mapping.js',lambda route:route.fulfill(status=403,content_type='application/json',body='{"error":"Access denied"}'))
  context.route('**/product-uploads.js',lambda route:route.fulfill(status=403,content_type='application/json',body='{"error":"Access denied"}'))
  baseline.goto('http://127.0.0.1:8793')
  with baseline.expect_response('**/product-uploads.js') as response:
   baseline.get_by_text('Mount workflow assets',exact=True).click()
  assert response.value.status==403
  assert baseline.evaluate('window.readyMessages.length')==0
  print('Old root-script 403 reproduced: no componentReady handshake. Live trigger remains unverified.')
  browser.close()
finally:
 server.terminate();server.wait(timeout=15);log.close()
