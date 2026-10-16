// Actual Streamlit editor/route, real loopback SQL jobs; external requests blocked.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const {execFileSync}=require('node:child_process');
const base='http://127.0.0.1:18897/';
async function sql(sql,args=[]){const r=await fetch('http://127.0.0.1:8873',{method:'POST',body:JSON.stringify({sql,args})});const data=await r.json();assert.equal(r.status,200,JSON.stringify(data));return data.rows;}
function worker(fail=false){execFileSync(process.env.CRM_TEST_PYTHON||'python',['-B','-c',`
import os,requests
from unittest.mock import patch
from contextlib import nullcontext
from tests.test_crm_send_flow import LIVE,CFG
from tests.crm_db_fixture import connect
from crm_automation_store import AutomationStore
from crm_automation_publication import tick
os.environ.update(LIVE)
requests.sessions.Session.request=lambda *a,**k:(_ for _ in ()).throw(AssertionError('External network forbidden'))
AutomationStore.render_settings=lambda *a,**k:CFG
with patch('crm_automation_publication.prepare',side_effect=ValueError('Email tracking failure')) if ${fail?'True':'False'} else nullcontext():
 tick(AutomationStore(connect),'browser-offline-worker',env=LIVE)
`],{env:{...process.env,CRM_TEST_POSTGRES:'1'},stdio:'pipe'});}
async function layout(page,width,error=false){
 const dialog=page.getByRole('dialog');await dialog.locator('[data-testid="stAlert"]').waitFor({state:error?'visible':'hidden'});
 await page.waitForTimeout(350);
 assert.equal(await dialog.count(),1);assert.equal(await page.locator('[data-sc-publication-dialog]').count(),1);
 const bounds=await dialog.boundingBox(),cancel=await dialog.getByRole('button',{name:'Cancel',exact:true}).boundingBox(),publish=await dialog.getByRole('button',{name:'Publish email',exact:true}).boundingBox();
 assert.ok(bounds.width<=Math.min(420,width-28),JSON.stringify(bounds));assert.ok(bounds.x>=0&&bounds.x+bounds.width<=width);
 assert.ok(cancel.x+cancel.width<=publish.x+1);assert.ok(Math.abs(cancel.y-publish.y)<2);
 assert.equal(await dialog.getByRole('button',{name:'Publish email',exact:true}).evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(200, 163, 70)');
 if(error){const alert=await dialog.getByTestId('stAlert').boundingBox();assert.ok(alert.y+alert.height<=publish.y+1);}
 assert.equal(await dialog.evaluate(e=>e.scrollWidth>e.clientWidth),false);
 return bounds;
}
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true}),results=[];
 try{
  await sql("UPDATE crm_automation_publish_jobs SET state='FAILED' WHERE state IN ('QUEUED','RUNNING') AND automation_id IN (SELECT id FROM crm_automations WHERE name IN ('Welcome Series','Collector follow-up'))");
  for(const scenario of [{width:1440,kind:'welcome',direct:true},{width:390,kind:'post_purchase',active:true},{width:320,kind:'welcome',validation:true},{width:390,kind:'welcome',lost:true}]){
   let page=await browser.newPage({viewport:{width:scenario.width,height:950}});page.setDefaultTimeout(15000);
   const setup=async p=>{await p.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());};await setup(page);
   try{
    const query=new URLSearchParams({run:'individual-'+Date.now(),kind:scenario.kind,...(scenario.active?{active:'1'}:{}),...(scenario.validation?{validation:'1'}:{}),...(scenario.lost?{lost:'1'}:{})});
    await page.goto(base+'?'+query);const rows=()=>page.locator('[class*="st-key-flow-row-"]');await rows().first().waitFor();
    const identity=await page.locator('#fixture-flow-id').getAttribute('data-id');
    const before=(await sql('SELECT * FROM crm_automations WHERE id=$1',[identity]))[0];
    await rows().first().getByRole('button',{name:/Edit Email/}).click();
    await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();
    if(scenario.direct){const url=page.url();await page.close();page=await browser.newPage({viewport:{width:scenario.width,height:950}});page.setDefaultTimeout(15000);await setup(page);await page.goto(url);await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();}
    const subject='Unsaved latest subject '+Date.now();await page.getByRole('textbox',{name:'Subject',exact:true}).fill(subject);
    const open=()=>page.getByRole('button',{name:'Publish Email',exact:true}).click();await open();
    const dialog=()=>page.getByRole('dialog');await dialog().getByRole('button',{name:'Cancel',exact:true}).waitFor();
    await page.waitForFunction(()=>document.activeElement?.textContent==='Cancel');await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(()=>document.activeElement?.textContent),'Publish email');
    await page.keyboard.press('Escape');await dialog().waitFor({state:'hidden'});
    await page.waitForFunction(()=>document.activeElement?.textContent==='Publish Email');await open();
    await dialog().getByRole('button',{name:'Publish email',exact:true}).waitFor();
    const bounds=await layout(page,scenario.width);
    await page.screenshot({path:`tmp/individual-publish-${scenario.width}${scenario.lost?'-lost':''}.png`});
    await dialog().getByRole('button',{name:'Publish email',exact:true}).dblclick();
    if(scenario.validation){
     await dialog().getByText(/Review the selected email/).waitFor();await layout(page,scenario.width,true);
     assert.ok(new URL(page.url()).searchParams.get('automation_email'));
     assert.equal((await sql('SELECT * FROM crm_automation_publish_jobs WHERE automation_id=$1',[identity])).length,0);
     await page.screenshot({path:'tmp/individual-publish-long-error.png'});results.push({...scenario,bounds,validation_retains_editor:true});continue;
    }
    if(scenario.lost){
     await dialog().getByText(/response interrupted/).waitFor();await layout(page,scenario.width,true);
     await dialog().getByRole('button',{name:'Publish email',exact:true}).click();
    }
    await dialog().waitFor({state:'hidden'});await rows().first().getByText('Publishing…',{exact:true}).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('automation'),identity);assert.equal(new URL(page.url()).searchParams.get('automation_email'),null);
    const parent=scenario.active?'Flow Active':'Flow Disabled';await page.getByText(parent,{exact:true}).waitFor();
    const pending=(await sql('SELECT * FROM crm_automations WHERE id=$1',[identity]))[0];
    assert.equal(pending.config.draft.emails[0].document.content.subject,subject);
    assert.equal((await sql('SELECT * FROM crm_automation_publish_jobs WHERE automation_id=$1 AND revision=$2',[identity,pending.config.publication.revision])).length,1);
    await page.reload();await rows().first().getByText('Publishing…',{exact:true}).waitFor();
    // Run the worker outside the UI: only the affected fragment should refresh.
    await page.evaluate(()=>{window.rowMounts=0;window.sequence=document.querySelector('[class*="st-key-flow-row-"]');window.observed=new MutationObserver(()=>{const node=document.querySelector('[class*="st-key-flow-row-"]');if(node&&node!==window.sequence){window.rowMounts++;window.sequence=node;}});window.observed.observe(document.body,{subtree:true,childList:true});});
    worker(true);await rows().first().getByText(/Publish failed/).waitFor();await page.getByText(parent,{exact:true}).waitFor();
    const failed=(await sql('SELECT * FROM crm_automations WHERE id=$1',[identity]))[0];assert.deepEqual(failed.steps,before.steps);assert.equal(failed.config.draft.emails[0].document.content.subject,subject);
    await rows().first().getByRole('button',{name:'Retry',exact:true}).click();await rows().first().getByText('Publishing…',{exact:true}).waitFor();
    worker();await rows().first().getByText('Published',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>window.rowMounts),0);
    const done=(await sql('SELECT * FROM crm_automations WHERE id=$1',[identity]))[0];
    assert.equal(done.status,before.status);assert.equal(done.activated_at,before.activated_at);
    const selected=done.steps.find(s=>s.step_id===done.config.draft.emails[0].step_id);
    const version=(await sql('SELECT content FROM crm_template_versions WHERE template_id=$1 AND version=$2',[selected.template_id,selected.template_version]))[0];
    assert.equal(version.content.document.content.subject,subject);
    assert.deepEqual(done.config.draft.emails.map(s=>s.enabled),[true,false,!!scenario.active]);
    assert.deepEqual(done.steps.filter(s=>s.step_id!==done.config.draft.emails[0].step_id),before.steps);
    assert.equal((await sql('SELECT * FROM crm_automation_enrollments WHERE automation_id=$1',[identity])).length,0);
    await page.reload();await rows().first().getByText('Published',{exact:true}).waitFor();await page.getByText(parent,{exact:true}).waitFor();
    results.push({...scenario,bounds,accepted_route:identity,refresh_pending:true,failed_retry:true,no_row_remounts:true,activation_preserved:true});
   }catch(e){console.error((await page.locator('body').innerText()).slice(0,4500));throw e;}finally{await page.close();}
  }
  const inline=await browser.newPage();inline.setDefaultTimeout(15000);
  try{
   await inline.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
   await inline.goto(base+'?run=inline-'+Date.now());
   const control=inline.getByRole('combobox',{name:/Status and actions for Fixture email 1$/});
   await control.click();await inline.getByRole('option',{name:'Publish email',exact:true}).click();
   await inline.getByRole('dialog').getByRole('button',{name:'Publish email',exact:true}).waitFor();
   await inline.keyboard.press('Escape');await inline.getByRole('dialog').waitFor({state:'hidden'});
   await control.click();await inline.getByRole('option',{name:'Enable in draft',exact:true}).click();
   await inline.locator('[class*="st-key-flow-state-draft-"]').waitFor();
   await control.click();await inline.getByRole('option',{name:'Disable in draft',exact:true}).waitFor();await inline.keyboard.press('Escape');
   results.push({inline_confirmation:true,inline_actions_stay_usable:true});
  }finally{await inline.close();}
  console.log(JSON.stringify(results,null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
