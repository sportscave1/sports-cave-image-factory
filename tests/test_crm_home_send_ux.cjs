// Synthetic loopback browser acceptance/progress only. No production requests.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const context=await browser.newContext();
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();
  await page.setViewportSize({width:1366,height:768});
  await page.goto('http://127.0.0.1:8525');
  await page.getByRole('button',{name:'Review & send',exact:true}).click();
  await page.getByRole('dialog').waitFor();
  await page.getByRole('button',{name:'Send to 1095 recipients',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  await page.locator('.sc-home-row').waitFor();
  await page.waitForFunction(()=>document.querySelector('.sc-home-row')?.textContent.includes('0 / 1,095'));
  for(const count of ['100 / 1,095','500 / 1,095']) {
   await page.waitForFunction(count=>document.querySelector('.sc-home-row')?.textContent.includes(count),count,{timeout:18000});
   assert.equal(await page.getByRole('dialog').count(),0);
   assert.equal(await page.locator('.st-key-crm-send-tray').count(),0);
   assert.equal(await page.getByTestId('stException').count(),0);
   console.log('Home durable progress: '+count);
  }
  await page.waitForFunction(()=>document.querySelector('.sc-home-row .sc-col-status')?.textContent.trim()==='Sent',null,{timeout:18000});
  assert.equal(await page.locator('.sc-home-send-bar').count(),0);
  assert.equal(await page.getByText('Fixture accepted jobs: 1',{exact:true}).count(),1);
  await page.reload();await page.locator('.sc-home-row').waitFor();
  assert.equal(await page.getByText('Fixture accepted jobs: 1',{exact:true}).count(),1);
  for(const width of [1366,750,390,320]) {
   await page.setViewportSize({width,height:768});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'No horizontal overflow');
   assert.equal(await page.getByRole('dialog').count(),0);
   assert.equal(await page.locator('.st-key-crm-send-tray').count(),0);
  }
  console.log('Accepted review closes; Home progresses 0 → 100 → 500 → SENT; reload makes no second job; 4 viewports contained.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
