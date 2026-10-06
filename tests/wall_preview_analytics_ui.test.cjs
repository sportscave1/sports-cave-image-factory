const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const page=await browser.newPage();
  await page.route('**/*',r=>r.request().url().startsWith('http://127.0.0.1:8877')?r.continue():r.abort());
  await page.goto('http://127.0.0.1:8877');
  await page.getByText('Wall Preview — Last 7 Days',{exact:true}).waitFor();
  for(const label of ['Overview','Wall Preview Inbox','Create','Plan','Playbook','Tracking'])await page.getByRole('button',{name:label,exact:true}).waitFor();
  await page.getByRole('button',{name:'View Wall Preview Analytics →',exact:true}).click();
  await page.getByText('Wall Preview performance',{exact:true}).waitFor();
  await page.getByRole('button',{name:/Open Wall Preview Folder/}).waitFor();
  await page.getByText('CRM intent',{exact:true}).waitFor();
  for(const width of [1920,1366,750,390,320]) {
   await page.setViewportSize({width,height:1000});await page.waitForTimeout(150);
   assert.equal(await page.getByTestId('stException').count(),0);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'overflow '+width);
   console.log('PASS analytics/inbox layout '+width+'px');
  }
  await page.setViewportSize({width:1366,height:1000});
  await page.getByRole('button',{name:/Details/}).click();
  await page.getByText('Anonymous visitor',{exact:true}).waitFor();
  await page.getByText('Journey',{exact:true}).waitFor();
  fs.mkdirSync('test-results/wall-preview-analytics',{recursive:true});
  await page.screenshot({path:'test-results/wall-preview-analytics/inbox.png',fullPage:true});
  await page.getByTestId('stMain').evaluate(e=>e.scrollTo(0,0));
  await page.screenshot({path:'test-results/wall-preview-analytics/analytics.png',fullPage:true});
  console.log('PASS Overview link, unchanged inbox controls, anonymous journey and no exceptions');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
