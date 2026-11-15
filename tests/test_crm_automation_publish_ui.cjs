// Local SQL + mock rendering config. Never runs Engine.tick or a mail transport.
const {chromium}=require('playwright');
const {spawnSync}=require('node:child_process');
const assert=require('node:assert/strict');
function worker(fail=false,expectedSubject=null,expectedHtml=null){
 const code=`from copy import deepcopy
from unittest.mock import patch
from crm_automation_store import AutomationStore
from crm_automation_publication import tick
from tests.crm_db_fixture import connect
from tests.test_crm_send_flow import CFG,LIVE
import sys
import json
store=AutomationStore(connect)
if len(sys.argv)>1:
 job=store.q("SELECT snapshot FROM crm_automation_publish_jobs WHERE state='QUEUED' ORDER BY requested_at LIMIT 1",one=True)
 assert job['snapshot']['flow']['emails'][0]['document']['content']['subject']==sys.argv[1], 'Saved snapshot is not latest widget content'
 if len(sys.argv)>2: assert sys.argv[2] in json.dumps(job['snapshot']), 'Pending section edit was not frozen'
with patch('requests.sessions.Session.request',side_effect=AssertionError('External I/O forbidden')),patch.object(store,'render_settings',return_value=deepcopy(CFG)):
 ${fail?"with patch('crm_automation_publication.prepare',side_effect=ValueError('Email tracking failed')): tick(store,'ui-fixture',env=LIVE)":"tick(store,'ui-fixture',env=LIVE)"}
`;
 const r=spawnSync('.venv/Scripts/python.exe',['-c',code,...(expectedSubject?[expectedSubject]:[]),...(expectedHtml?[expectedHtml]:[])],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1',CRM_TEST_POSTGRES:'1'}});
 assert.equal(r.status,0,r.stderr);
}
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext();
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();page.setDefaultTimeout(15000);
  const toolbar=page.locator('.st-key-automation-toolbar');
  const start=async suffix=>{
   await page.goto('http://127.0.0.1:8533/?fixture_checkout=1&fixture_run='+suffix+Date.now());
   await page.getByRole('button',{name:'Edit Email',exact:true}).first().click();
   await toolbar.getByRole('button',{name:'Publish now',exact:true}).waitFor();
  };
  for(const width of [1440,390]){
   await page.setViewportSize({width,height:950});await start('publish');
   const subject='Local publish '+width+' '+Date.now();
   await page.getByRole('textbox',{name:'Subject',exact:true}).fill(subject);
   const started=Date.now();await toolbar.getByRole('button',{name:'Publish now',exact:true}).click();
   await toolbar.getByText('Publishing changes…',{exact:true}).waitFor();
   assert.equal(await page.locator('.st-key-flow-workspace').count(),0,'Publishing must retain the editor');
   assert.equal(await page.getByRole('textbox',{name:'Subject',exact:true}).inputValue(),subject);
   const elapsed=Date.now()-started;assert.ok(elapsed<5000,'Local publication acknowledgement took '+elapsed+'ms');
   assert.equal(await page.getByTestId('stException').count(),0);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
   // Refresh reconstructs status from SQL, never a browser-owned job.
   await page.reload();await toolbar.getByText('Publishing changes…',{exact:true}).waitFor();
   await page.waitForFunction(()=>{const el=document.querySelector('.sc-flow-stats dd');return el&&el.textContent!=='—';});
   await page.evaluate(()=>{window.summaryMutations=0;new MutationObserver(()=>window.summaryMutations++).observe(document.querySelector('.sc-flow-stats'),{subtree:true,childList:true,characterData:true});});
   const began=Date.now();worker(false,subject);
   await toolbar.getByText('Published · Up to date',{exact:true}).waitFor();
   assert.equal(await page.evaluate(()=>summaryMutations),0,'Status polling must not rebuild analytics');
   console.log(`Publish ${width}px: accepted in editor in ${elapsed}ms; separate worker + observed status ${Date.now()-began}ms`);
  }
  await page.setViewportSize({width:1440,height:950});
  await start('html');
  const currentSubject=await page.getByRole('textbox',{name:'Subject',exact:true}).inputValue();
  // Subject flushing is tested above; isolate the independent pending-HTML
  // acknowledgement here without racing a native subject blur rerun.
  await page.getByRole('tab',{name:'Editor',exact:true}).click();
  const area=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]').getByRole('textbox').first();
  const marker='Latest section '+Date.now();await area.fill((await area.inputValue())+'<p>'+marker+'</p>');
  await toolbar.getByRole('button',{name:'Publish now',exact:true}).click();await toolbar.getByText('Publishing changes…',{exact:true}).waitFor();
  const returnUrl=page.url();await page.goto('about:blank');
  worker(false,currentSubject,marker);await page.goto(returnUrl);
  await toolbar.getByText('Published · Up to date',{exact:true}).waitFor();
  console.log('Immediate publish freezes latest pending HTML; worker completes while browser is away');
  await start('invalid');await page.getByRole('textbox',{name:'Subject',exact:true}).fill('');
  await toolbar.getByRole('button',{name:'Publish now',exact:true}).click();
  await page.getByText('Add a subject before publishing.',{exact:true}).waitFor();
  assert.equal(await page.locator('.st-key-flow-workspace').count(),0);
  await page.getByRole('textbox',{name:'Subject',exact:true}).fill('Retry publication fixture');
  await toolbar.getByRole('button',{name:'Publish now',exact:true}).click();await toolbar.getByText('Publishing changes…',{exact:true}).waitFor();
  worker(true);await page.getByText(/Publishing failed · Email tracking/).waitFor();
  await toolbar.getByRole('button',{name:'Retry Publish',exact:true}).click();await toolbar.getByText('Publishing changes…',{exact:true}).waitFor();
  worker(false);await toolbar.getByText('Published · Up to date',{exact:true}).waitFor();
  assert.equal(await page.getByTestId('stException').count(),0);
  console.log('Invalid subject retains editor; durable failure clears spinner and Retry Publish succeeds without leaving the editor');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
