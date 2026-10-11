// Existing synthetic Streamlit + disposable SQL fixture. All remote requests denied.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const evidence=[];const errors=[];
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  page.on('pageerror',e=>errors.push(e.message));
  const base=process.env.FLOW_URL||'http://127.0.0.1:18606/';
  const rows=page.locator('[class*="st-key-flow-row-"]');
  for(const kind of ['welcome','post_purchase','win_back','abandoned','fulfilled']){
   const started=Date.now();
   await page.goto(base+'?fixture_empty='+kind+'&fixture_run=empty-contract-'+Date.now());
   await page.locator('.sc-flow-empty').waitFor();
   assert.equal(await page.getByRole('button',{name:'Test',exact:true}).count(),1);
   const openMs=Date.now()-started;
   assert.equal(await rows.count(),0);
   assert.equal(await page.getByRole('button',{name:'Prepare draft flow',exact:true}).count(),0);
   assert.equal(await page.locator('.sc-flow-stats dt').count(),8);
   for(const width of [1440,750,390,320]){
    await page.setViewportSize({width,height:1000});
    await page.evaluate(()=>window.scrollTo(0,0));
    const y=await page.locator('.st-key-automation-toolbar').evaluate(e=>e.getBoundingClientRect().top);
    assert.ok(y>=64 && y<=80,kind+' header y='+y);
    assert.equal(await page.getByTestId('stMain').evaluate(e=>e.scrollWidth>e.clientWidth+2),false);
    evidence.push({kind,width,headerY:y,openMs});
   }
   await page.reload();await page.locator('.sc-flow-empty').waitFor();assert.equal(await rows.count(),0);
   await page.setViewportSize({width:1440,height:1000});
   await page.getByRole('button',{name:'+ Add Email',exact:true}).click();
   await rows.first().waitFor();assert.equal(await rows.count(),1);
   await page.getByRole('button',{name:'Edit Email',exact:true}).click();
   const subject=page.getByRole('textbox',{name:'Subject',exact:true});await subject.waitFor();
   await subject.fill('Saved '+kind+' email');await subject.press('Tab');
   await page.getByRole('button',{name:'Flow',exact:true}).click();
   await page.getByText('Saved '+kind+' email',{exact:true}).waitFor();
   await page.reload();await page.getByText('Saved '+kind+' email',{exact:true}).waitFor();assert.equal(await rows.count(),1);
   for(const width of [1440,320]){
    await page.setViewportSize({width,height:1000});
    assert.equal(await page.getByTestId('stMain').evaluate(e=>e.scrollWidth>e.clientWidth+2),false);
    fs.mkdirSync('.tmp-flow-page-fix',{recursive:true});
    await page.screenshot({path:'.tmp-flow-page-fix/'+kind+'-'+width+'.png',fullPage:true});
   }
   await page.getByRole('button',{name:'← Automations',exact:true}).click();await page.locator('.sc-auto-kpi').first().waitFor();
   assert.equal(await page.getByTestId('stException').count(),0);
  }
  for(const kind of ['welcome','post_purchase','win_back','abandoned']){
   await page.goto(base+'?fixture_existing='+kind+'&fixture_run=preserve-'+Date.now());
   await rows.first().waitFor();
   const before=await page.locator('.sc-flow-copy').allTextContents();
   assert.equal(before.length,kind==='abandoned'?3:1);
   assert.equal(await page.getByRole('button',{name:'Prepare draft flow',exact:true}).count(),0);
   await page.reload();await rows.first().waitFor();
   assert.deepEqual(await page.locator('.sc-flow-copy').allTextContents(),before);
  }
  await page.goto(base+'?fixture_uninitialised=welcome&fixture_run=unused-'+Date.now());
  await page.locator('.sc-flow-empty').waitFor();assert.equal(await rows.count(),0);
  await page.reload();await page.locator('.sc-flow-empty').waitFor();assert.equal(await rows.count(),0);
  assert.deepEqual(errors,[]);
  fs.mkdirSync('.tmp-flow-page-fix',{recursive:true});
  fs.writeFileSync('.tmp-flow-page-fix/browser-results.json',JSON.stringify(evidence,null,2));
  console.log('PASS: five triggers, zero emails, refresh, Add/Edit/Save, back navigation, four viewport widths',JSON.stringify(evidence));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
