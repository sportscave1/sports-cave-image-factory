"""Offline browser regression; requires the loopback CRM SQL and picker fixtures."""
import os,sys,json
from pathlib import Path
from urllib.parse import urlparse,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('CRM_FIXTURE_SQL_PORT','8897')
from tests.crm_db_fixture import connect
from playwright.sync_api import sync_playwright, expect

def reset_fixture(identity):
 with connect() as c:
  row=c.execute("SELECT id,document FROM crm_campaign_drafts WHERE name='Collection picker fixture' AND id=%s",(identity,)).fetchone()
  for section in row['document']['middle_sections']:
   if section['type']=='catalogue':section['products']=[]
  c.execute('UPDATE crm_campaign_drafts SET document=%s::jsonb,version=version+1 WHERE id=%s',(json.dumps(row['document']),row['id']))

with sync_playwright() as p:
 b=p.chromium.launch(channel=os.getenv('PICKER_BROWSER','chrome'),headless=True)
 page=b.new_page(viewport={'width':int(os.getenv('PICKER_WIDTH','1440')),'height':1000},has_touch=int(os.getenv('PICKER_WIDTH','1440'))<500)
 page.route('**/*',lambda route:route.continue_() if urlparse(route.request.url).hostname in ('127.0.0.1','localhost') else route.abort())
 page.goto(os.getenv('PICKER_URL','http://127.0.0.1:8541'))
 page.get_by_role('link',name='Collection picker fixture',exact=True).first.wait_for()
 identity=parse_qs(urlparse(page.get_by_role('link',name='Collection picker fixture',exact=True).first.get_attribute('href')).query)['campaign'][0]
 reset_fixture(identity)
 page.reload()
 page.locator('a[href*="campaign='+identity+'"]').click()
 page.get_by_role('tab',name='Editor',exact=True).click()
 frame=page.frame_locator('iframe[title="crm_section_ui.crm_middle_sections_v2"]')
 frame.locator('.catalogue button.title').click()
 frame.get_by_role('button',name='Select products',exact=False).click()
 page.get_by_role('dialog').get_by_text('Selected: 0 / 12',exact=True).wait_for()
 def choose(name):
  page.get_by_role('dialog').get_by_role('combobox').click()
  option=page.get_by_role('option',name=name,exact=True)
  assert option.evaluate('(el)=>{const r=el.getBoundingClientRect();const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return hit===el||el.contains(hit)}')
  if name=='Motorsport':
   evidence=Path(os.getenv('PICKER_EVIDENCE','tmp/picker-evidence'));evidence.mkdir(parents=True,exist_ok=True)
   page.screenshot(path=str(evidence/('dropdown-'+os.getenv('PICKER_BROWSER','chrome')+'-'+os.getenv('PICKER_WIDTH','1440')+'.png')))
  option.click()
  try:
   page.wait_for_function("(name)=>{const el=document.querySelector('[role=dialog] [data-testid=stSelectbox]');return el&&(el.textContent.includes(name)||el.querySelector('[role=combobox]')?.value===name)}",arg=name,timeout=10000)
  except Exception:
   print('Collection selection diagnostic:',page.get_by_role('dialog').inner_text(),page.locator('[role=dialog] [data-testid=stSelectbox]').evaluate('(el)=>el.outerHTML'),flush=True)
   page.screenshot(path=str(Path(os.getenv('PICKER_EVIDENCE','tmp'))/'failure-collection-selection.png'),full_page=True)
   raise
 choose('Motorsport')
 page.get_by_role('checkbox',name='Select Artwork 3',exact=True).wait_for(state='detached')
 page.locator('label').filter(has=page.get_by_role('checkbox',name='Select Artwork 1',exact=True)).click()
 try:
  page.get_by_role('dialog').get_by_text('Selected: 1 / 12',exact=True).wait_for(timeout=10000)
 except Exception:
  page.screenshot(path=str(Path(os.getenv('PICKER_EVIDENCE','tmp'))/'failure-first-selection.png'),full_page=True)
  print('picker failure state',page.get_by_role('dialog').inner_text())
  raise
 page.locator('label').filter(has=page.get_by_role('checkbox',name='Select Artwork 2',exact=True)).click()
 page.get_by_role('dialog').get_by_text('Selected: 2 / 12',exact=True).wait_for()
 choose('Tennis')
 page.get_by_role('checkbox',name='Select Artwork 1',exact=True).wait_for(state='detached')
 page.locator('label').filter(has=page.get_by_role('checkbox',name='Select Artwork 3',exact=True)).click()
 page.get_by_role('dialog').get_by_text('Selected: 3 / 12',exact=True).wait_for()
 choose('Motorsport')
 page.get_by_role('checkbox',name='Select Artwork 1',exact=True).wait_for(state='attached')
 page.wait_for_timeout(600)
 assert page.get_by_role('checkbox',name='Select Artwork 1',exact=True).is_checked()
 assert page.get_by_role('checkbox',name='Select Artwork 2',exact=True).is_checked()
 page.get_by_role('button',name='Add selected',exact=True).click()
 page.get_by_role('dialog').wait_for(state='hidden')
 expect(frame.get_by_role('button',name='Select products',exact=False)).to_be_focused(timeout=10000)
 page.wait_for_timeout(1500)
 if frame.locator('.catalogue button.title').get_attribute('aria-expanded')!='true':frame.locator('.catalogue button.title').click()
 print('products after add',frame.locator('.catalogue .product-info').all_text_contents())
 assert frame.locator('.catalogue .product-info').all_text_contents()==['Artwork 1','Artwork 2','Artwork 3']
 page.get_by_role('button',name='← Campaigns',exact=True).click()
 page.locator('a[href*="campaign='+identity+'"]').click()
 page.get_by_role('tab',name='Editor',exact=True).click()
 frame.locator('.catalogue button.title').click()
 print('products after reopen',frame.locator('.catalogue .product-info').all_text_contents())
 assert frame.locator('.catalogue .product-info').all_text_contents()==['Artwork 1','Artwork 2','Artwork 3']
 assert any(all(('Artwork '+str(i)) in f.content() for i in (1,2,3)) for f in page.frames if f!=page.main_frame and f.frame_element().get_attribute('title')!='crm_section_ui.crm_middle_sections_v2'), 'Saved catalogue missing from email preview'
 output=Path(os.getenv('PICKER_EVIDENCE','tmp/picker-evidence'));output.mkdir(parents=True,exist_ok=True)
 page.screenshot(path=str(output/(os.getenv('PICKER_BROWSER','chrome')+'-'+os.getenv('PICKER_WIDTH','1440')+'.png')),full_page=True)
 b.close()
