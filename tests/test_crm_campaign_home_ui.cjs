// Run only against the synthetic loopback preview. No production requests.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const context=await browser.newContext();
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  let page=await context.newPage();
  for(const [width,height] of [[1920,1080],[1366,768],[750,900],[390,844],[320,740]]){
   await page.setViewportSize({width,height});await page.goto('http://127.0.0.1:8531');
   await page.getByRole('button',{name:'+ New campaign',exact:true}).waitFor();
   await page.locator('.sc-home-row').first().waitFor();
   await page.waitForFunction(()=>document.querySelectorAll('.sc-home-row').length===4);
   assert.equal(await page.getByTestId('stException').count(),0);
   const bounds=await page.evaluate(()=>({body:document.documentElement.scrollWidth,
     breadcrumb:document.querySelector('.sc-home-breadcrumb').getBoundingClientRect().top,
     main:document.querySelector('.st-key-crm-campaign-home').getBoundingClientRect().toJSON(),
     table:document.querySelector('.st-key-crm-home-table').getBoundingClientRect().toJSON(),
     cards:getComputedStyle(document.querySelector('.sc-home-kpis')).gridTemplateColumns.split(' ').length,
     scroll: [...document.querySelectorAll('.st-key-crm-home-table,.st-key-crm-home-table *')].filter(e=>
       e.scrollHeight>e.clientHeight+2 && ['auto','scroll'].includes(getComputedStyle(e).overflowY)).length,
     rowOverflow:[...document.querySelectorAll('.sc-home-row')].some(e=>e.scrollWidth>e.clientWidth+2)}));
   assert(bounds.body<=width,'No document overflow');
   assert.equal(bounds.scroll,0,'No internal table vertical scrollbar');
   assert.equal(bounds.rowOverflow,false,'No row horizontal overflow');
   assert.equal(await page.getByTestId('stRadio').count(),0,'No radio/dot tabs');
   assert.equal(await page.locator('.st-key-crm-home-tabs input[type=radio]').count(),0);
   assert.equal(await page.locator('.st-key-crm-home-tabs button[kind=segmented_controlActive]').evaluate(e=>getComputedStyle(e).borderBottomColor),'rgb(199, 161, 63)');
   assert.equal(await page.locator('.sc-home-icon img').count(),5);
   assert.equal(bounds.cards,width>1200?5:width>700?3:2);
   if(width>=1366){
    assert(bounds.table.width>bounds.main.width*.94,'Table uses available width');
    assert(bounds.breadcrumb<100,'Compact top gutter');
    const filter=page.getByRole('button',{name:'Filter',exact:false});
    assert((await filter.boundingBox()).width>=90,'Filter remains readable');
   }
   const values=await page.locator('.sc-home-kpis').innerText();
   await page.getByPlaceholder('Search campaigns…').fill('Ryan Fox');
   await page.getByPlaceholder('Search campaigns…').press('Enter');
   await page.waitForFunction(()=>document.querySelectorAll('.sc-home-row').length===1);
   assert.equal(await page.locator('.sc-home-row').count(),1,'Search updates rows');
   assert.equal(await page.locator('.sc-home-kpis').innerText(),values,'Search preserves KPIs');
   await page.getByPlaceholder('Search campaigns…').fill('');await page.getByPlaceholder('Search campaigns…').press('Enter');
   await page.waitForFunction(()=>document.querySelectorAll('.sc-home-row').length===4);
   if(process.env.CAMPAIGN_HOME_EVIDENCE_DIR)await page.screenshot({path:path.join(process.env.CAMPAIGN_HOME_EVIDENCE_DIR,'campaign-home-after-'+width+'.png'),fullPage:true});
   console.log(width+': contained, '+bounds.cards+' KPIs across; gutter '+bounds.breadcrumb.toFixed(1)+'px; full-width table, no nested scroll; stable search');
  }
  await page.close();page=await context.newPage();
  await page.setViewportSize({width:1366,height:768});
  const started=Date.now();await page.goto('http://127.0.0.1:8531/?mode=slow');
  await page.getByRole('button',{name:'+ New campaign',exact:true}).waitFor();
  const shell=Date.now()-started;
  await page.locator('.sc-home-kpis').waitFor();
  assert(await page.locator('.sc-home-unresolved').count()>0,'Shell emitted before slow reads finish');
  await page.locator('.sc-home-row').first().waitFor();const rows=Date.now()-started;
  await page.waitForFunction(()=>document.querySelector('.sc-home-kpis').textContent.includes('NZ$250.00'));
  const complete=Date.now()-started;
  const good=await page.locator('.sc-home-kpis').innerText();
  await page.getByRole('button',{name:'Simulate delivery outage',exact:true}).click();
  await page.waitForTimeout(500);
  assert.equal(await page.locator('.sc-home-kpis').innerText(),good,'READY values stay during REFRESHING');
  await page.getByText('Some totals are temporarily unavailable · last resolved values retained.',{exact:true}).waitFor();
  assert.equal(await page.locator('.sc-home-kpis').innerText(),good,'One failed group preserves all resolved facts');
  assert.equal(await page.getByTestId('stException').count(),0);
  assert.equal(await page.locator('.sc-home-unresolved').count(),0,'No resolved metric returns to skeleton');
  console.log(`Slow-read fixture: shell ${shell}ms, rows ${rows}ms, all KPI groups ${complete}ms; refresh/outage stable. Synthetic delays only.`);
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
