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
  const page=await context.newPage();
  for(const width of [1920,1366,750,390,320]){
   await page.setViewportSize({width,height:950});
   await page.goto('http://127.0.0.1:8533/?fixture_checkout=1&fixture_home_delay=1');
   const publish=page.getByRole('button',{name:'Publish now',exact:true});await publish.waitFor();
   assert.equal(await page.getByText('This email copy is reviewed',{exact:true}).count(),0);
   const subject='Local publish '+width+' '+Date.now();
   await page.getByRole('textbox',{name:'Subject',exact:true}).fill(subject);
   const started=Date.now();await publish.click();
   await page.getByRole('heading',{name:'Automations',exact:true}).waitFor();
   const row=page.locator('[class*=st-key-auto-row-]').filter({hasText:'Abandoned checkout · local fixture'}).first();
   await row.getByText('Publishing…',{exact:true}).waitFor();
   await page.getByRole('textbox',{name:'Search automations',exact:true}).isEnabled().then(v=>assert.equal(v,true));
   await row.locator('[data-testid=stPopoverButton]:visible').click();await page.getByRole('button',{name:'Open editor',exact:true}).waitFor();await page.keyboard.press('Escape');
   const elapsed=Date.now()-started;assert.ok(elapsed<5000,'Local UI navigation took '+elapsed+'ms');
   assert.equal(await page.getByTestId('stException').count(),0);
   const geometry=await page.evaluate(()=>({width:innerWidth,body:document.documentElement.scrollWidth}));
   assert.ok(geometry.body<=width+2,JSON.stringify(geometry));
   await page.waitForFunction(()=>document.querySelectorAll('.sc-auto-kpis .sc-home-unresolved').length===0);
   await page.waitForFunction(()=>!document.querySelector('.st-key-auto-activity')?.textContent.includes('Loading recent activity'));
   await page.evaluate(()=>{
    window.homeSecondaryMutations=0;
    for(const selector of ['.sc-auto-kpis','.st-key-auto-activity']){
     const el=document.querySelector(selector);if(el)new MutationObserver(()=>window.homeSecondaryMutations++).observe(el,{subtree:true,childList:true,characterData:true});
    }
   });
   worker(false,subject); // Separate process; the browser only observes durable completion.
   await row.getByText('Live',{exact:true}).waitFor({timeout:12000});
   assert.equal(await row.getByText('Publishing…',{exact:true}).count(),0);
   assert.equal(await page.evaluate(()=>window.homeSecondaryMutations),0,'Publication status changed secondary regions');
   console.log(`Publish ${width}px: accepted/home in ${elapsed}ms; durable worker → Live; no overflow`);
  }
  await page.goto('http://127.0.0.1:8533/?fixture_checkout=1&fixture_home_delay=1');await page.getByRole('button',{name:'Publish now',exact:true}).waitFor();
  const currentSubject=await page.getByRole('textbox',{name:'Subject',exact:true}).inputValue();
  await page.getByRole('tab',{name:'Editor',exact:true}).click();
  const area=page.frameLocator('iframe[src*="crm_middle_sections"]').getByRole('textbox',{name:'HTML Section 1 HTML',exact:true});
  const marker='Latest section '+Date.now();await area.fill((await area.inputValue())+'<p>'+marker+'</p>');
  await page.getByRole('button',{name:'Publish now',exact:true}).click();
  await page.getByRole('heading',{name:'Automations',exact:true}).waitFor();
  worker(false,currentSubject,marker);
  await page.locator('[class*=st-key-auto-row-]').filter({hasText:'Abandoned checkout · local fixture'}).first().getByText('Live',{exact:true}).waitFor({timeout:12000});
  console.log('Immediate publish flushes pending HTML section and freezes exact latest content');
  // Real immediate validation remains in the editor, without queue acceptance.
  await page.goto('http://127.0.0.1:8533/?fixture_checkout=1&fixture_home_delay=1');await page.getByRole('button',{name:'Publish now',exact:true}).waitFor();
  await page.getByRole('textbox',{name:'Subject',exact:true}).fill('');
  await page.getByRole('textbox',{name:'Subject',exact:true}).press('Tab');
  await page.getByRole('button',{name:'Publish now',exact:true}).click();
  await page.getByText('Add a subject before publishing.',{exact:true}).waitFor();
  assert.equal(await page.getByRole('heading',{name:'Automations',exact:true}).count(),0);
  await page.getByRole('textbox',{name:'Subject',exact:true}).fill('Local failed attempt '+Date.now());
  await page.getByRole('textbox',{name:'Subject',exact:true}).press('Tab');
  await page.getByRole('button',{name:'Publish now',exact:true}).click();
  await page.getByRole('heading',{name:'Automations',exact:true}).waitFor();
  const row=page.locator('[class*=st-key-auto-row-]').filter({hasText:'Abandoned checkout · local fixture'}).first();
  await row.getByText('Publishing…',{exact:true}).waitFor();worker(true);
  await row.getByText('Publish failed',{exact:true}).waitFor({timeout:12000});
  await row.locator('[data-testid=stPopoverButton]:visible').click();
  await page.getByRole('button',{name:'Open editor',exact:true}).click();
  await page.getByText('Email tracking validation failed. Review the email before publishing.',{exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Publish now',exact:true}).isEnabled(),true);
  console.log('Missing subject stays in editor; durable failure opens actionable reason and permits retry');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
