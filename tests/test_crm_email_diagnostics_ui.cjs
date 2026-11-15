// Existing automation UI, disposable SQL, external network blocked.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();
  await page.goto((process.env.CRM_FIXTURE_UI_URL||'http://127.0.0.1:8562')+'/?fixture_toolbar_live=1&fixture_run=diagnostics'+Date.now());
  const toolbar=page.locator('.st-key-automation-toolbar');
  await toolbar.getByRole('button',{name:'Diagnostics',exact:true}).click();
  await page.getByText('Shopify trigger diagnostic',{exact:true}).click();
  await page.getByText(/Published v1/).waitFor();
  await page.getByText(/Draft edits do not change delivery until published/).waitFor();
  await page.getByText(/0 accepted by Resend/).waitFor();
  assert.equal(await page.getByTestId('stException').count(),0);
  await page.screenshot({path:'tmp/email-diagnostics-desktop.png',fullPage:true});
  await page.keyboard.press('Escape');
  for(const width of [1440,1024,750,390]){
   await page.setViewportSize({width,height:1000});
   assert.equal(await toolbar.evaluate(e=>e.scrollWidth>e.clientWidth+2),false,`toolbar overflow at ${width}`);
  }
  assert.equal(await page.getByRole('button',{name:'Pause',exact:true}).count(),1);
  console.log('PASS read-only diagnostics, published/draft separation, zero acceptance, unchanged lifecycle and responsive toolbar');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
