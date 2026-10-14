// Synthetic fixture only; no external browser requests or live provider sends.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');const fs=require('node:fs');
(async()=>{
 const b=await chromium.launch({channel:'chrome',headless:true});
 let p;
 try{
  p=await b.newPage({viewport:{width:1440,height:1000}});const errors=[];const timings=[];
  p.on('pageerror',e=>{errors.push(e.message);console.error('Browser error:',e.message)});
  await p.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const base=process.env.FLOW_URL||'http://127.0.0.1:18606/';
  const rows=p.locator('[class*="st-key-flow-row-"]');
  const title=p.locator('.automation-title strong');
  const runs=()=>p.locator('#inline-full-runs').getAttribute('data-runs');
  async function select(locator,value){await locator.click();await p.getByRole('option',{name:value,exact:true}).click();}
  for(const kind of ['welcome','post_purchase','win_back','abandoned','fulfilled']){
   console.log('Checking',kind);
   await p.goto(base+'?fixture_existing='+kind+'&fixture_inline=1&fixture_run=v3-'+Date.now());
   await rows.first().waitFor();await p.locator('#inline-full-runs').waitFor({state:'attached'});
   const full=await runs();const original=await title.innerText();
   assert.equal(await rows.getByRole('button',{name:'⋮',exact:true}).count(),0);
   assert.equal(await p.getByRole('checkbox',{name:'Enable this email',exact:true}).count(),0);
   await p.getByRole('button',{name:/Rename automation/}).click();
   let name=p.getByRole('textbox',{name:'Automation name',exact:true});await name.fill('Discard this name');await name.press('Escape');
   await title.waitFor();assert.equal(await title.innerText(),original);
   await p.getByRole('button',{name:/Rename automation/}).click();await name.fill('V3 '+kind);await name.press('Enter');
   await p.getByText('V3 '+kind,{exact:true}).waitFor();
   await p.getByRole('button',{name:/Rename automation/}).click();await name.fill('   ');await name.press('Enter');
   await p.getByText('Use a name of 1-150 characters.',{exact:true}).waitFor();
   await name.fill('Saved '+kind);await p.locator('.sc-flow-stats').click();await p.getByText('Saved '+kind,{exact:true}).waitFor();
   assert.equal(await runs(),full,'rename stays inside toolbar fragment');
   if(await rows.count()<2){await p.getByRole('button',{name:'+ Add Email',exact:true}).click();await rows.nth(1).waitFor();}
   const firstClass=await rows.first().getAttribute('class');
   assert.equal(await rows.first().getByRole('button',{name:/Move up/}).isDisabled(),true);
   assert.equal(await rows.last().getByRole('button',{name:/Move down/}).isDisabled(),true);
   const start=Date.now();
   let delay=rows.first().getByRole('spinbutton');await delay.fill('3');await delay.press('Enter');
   await rows.first().getByText(/3 .* after/).waitFor();
   await select(rows.first().locator('[class*="st-key-flow-inline-"]').getByRole('combobox'),'Days');
   await rows.first().getByText(/3 days after/).waitFor();timings.push({kind,delayMs:Date.now()-start});
   await rows.first().getByRole('button',{name:/Move down/}).click();
   await p.waitForFunction(c=>document.querySelectorAll('[class*="st-key-flow-row-"]')[1]?.className===c,firstClass);
   await rows.nth(1).getByRole('button',{name:/Move up/}).click();
   await p.waitForFunction(c=>document.querySelector('[class*="st-key-flow-row-"]')?.className===c,firstClass);
   assert.equal(await runs(),full,'delay/add/move stay inside sequence fragment');
   const count=kind==='abandoned'?3:2;
   await p.waitForFunction(n=>document.querySelectorAll('[class*="st-key-flow-row-"]').length===n,count);
   await rows.last().getByRole('button',{name:/Delete email/}).click();
   await p.getByRole('dialog').getByRole('button',{name:'Cancel',exact:true}).click();await p.getByRole('dialog').waitFor({state:'hidden'});
   await p.waitForFunction(n=>document.querySelectorAll('[class*="st-key-flow-row-"]').length===n,count);
   await rows.last().getByRole('button',{name:/Delete email/}).click();
   await p.getByRole('dialog').getByRole('button',{name:'Delete email',exact:true}).click();
   await p.getByRole('dialog').waitFor({state:'hidden'});
   await p.waitForFunction(n=>document.querySelectorAll('[class*="st-key-flow-row-"]').length===n,count-1);
   await p.reload();await rows.first().waitFor();assert.equal(await rows.count(),count-1);assert.equal(await title.innerText(),'Saved '+kind);
   await rows.first().getByText(/3 days after/).waitFor();
   await rows.first().getByRole('button',{name:/Edit Email/}).click();
   const subject=p.getByRole('textbox',{name:'Subject',exact:true});await subject.fill('Inline editor '+kind);await subject.press('Tab');
   await p.getByRole('button',{name:'Flow',exact:true}).click();await rows.first().getByText('Inline editor '+kind,{exact:true}).waitFor();
   for(const width of [1440,1024,750,390,320]){
    await p.setViewportSize({width,height:1000});
    assert.equal(await p.getByTestId('stMain').evaluate(e=>e.scrollWidth>e.clientWidth+2),false,kind+' overflow '+width);
    assert.equal(await rows.first().locator('.sc-flow-copy').evaluate(e=>getComputedStyle(e.querySelector('p')).cursor),'default');
    assert.equal(await rows.first().getByRole('spinbutton').evaluate(e=>getComputedStyle(e).cursor),'text');
    assert.equal(await rows.first().getByRole('button',{name:/Edit Email/}).evaluate(e=>getComputedStyle(e).cursor),'pointer');
    assert.equal(await rows.locator('[contenteditable="true"]').count(),0);
    if(kind==='abandoned'){fs.mkdirSync('.tmp-flow-v3',{recursive:true});await p.screenshot({path:'.tmp-flow-v3/inline-'+width+'.png',fullPage:true});}
   }
   await p.setViewportSize({width:1440,height:1000});
   assert.equal(await p.getByTestId('stException').count(),0);
  }
  // The existing published fixture uses a mock provider; no delivery worker runs.
  await p.goto(base+'?fixture_toolbar_live=1&fixture_inline=1&fixture_run=state-'+Date.now());await rows.first().waitFor();
  let status=rows.first().locator('[class*="st-key-flow-state-"]').getByRole('combobox');
  await select(status,'Pause flow');await rows.first().locator('[class*="st-key-flow-state-paused-"]').waitFor();
  await select(status,'Resume flow');await rows.first().locator('[class*="st-key-flow-state-live-"]').waitFor();
  const liveDelay=rows.first().getByRole('spinbutton');await liveDelay.fill('17');await liveDelay.press('Enter');
  await rows.first().getByText(/17 minutes after/).waitFor();
  await select(status,'Publish flow');await p.getByRole('dialog').getByRole('button',{name:'Publish All',exact:true}).click();await p.locator('.automation-publishing').waitFor();
  assert.equal(await rows.first().locator('[class*="st-key-flow-state-live-"]').count(),1,'pending publication keeps the previous live version');
  await p.getByRole('button',{name:'+ Add Email',exact:true}).click();await rows.nth(2).waitFor();
  assert.equal(await rows.last().locator('[class*="st-key-flow-state-draft-"]').count(),1);
  await select(rows.first().locator('[class*="st-key-flow-state-"]').getByRole('combobox'),'Disable in draft');
  await rows.first().getByText(/Disabled in draft/).waitFor();assert.equal(await rows.first().locator('[class*="st-key-flow-state-live-"]').count(),1);
  await p.getByRole('button',{name:'Pause',exact:true}).click();await rows.first().locator('[class*="st-key-flow-state-paused-"]').waitFor();
  await p.goto(base+'?fixture_empty=welcome&fixture_inline=1&fixture_run=locked-'+Date.now());await p.getByRole('button',{name:'+ Add Email',exact:true}).click();await rows.first().waitFor();
  await rows.first().locator('[class*="st-key-flow-state-"]').getByRole('combobox').click();
  assert.equal(await p.getByRole('option',{name:'Publish flow',exact:true}).count(),0);await p.keyboard.press('Escape');
  await p.getByText('Draft only: publishing is locked for this flow.',{exact:true}).waitFor();
  assert.deepEqual(errors,[]);fs.writeFileSync('.tmp-flow-v3/interaction-results.json',JSON.stringify(timings,null,2));console.log('PASS inline flow contracts',JSON.stringify(timings));
 }catch(e){if(p){console.log((await p.locator('body').innerText()).slice(0,2500));await p.screenshot({path:'.tmp-flow-v3/failure.png',fullPage:true});}throw e;}finally{await b.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
