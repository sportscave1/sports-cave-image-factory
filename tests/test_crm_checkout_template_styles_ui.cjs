// Local fixture and intercepted assets only; no transport or production writes.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1366,height:900}});
  await context.route('**/*',r=>{
   const u=new URL(r.request().url());
   if(u.hostname==='127.0.0.1')return r.continue();
   if(u.href==='https://cdn.shopify.com/fixture.png')return r.fulfill({contentType:'image/png',body:fs.readFileSync('tests/fixtures/checkout_product_generated.png')});
   return r.abort();
  });
  const page=await context.newPage();await page.goto('http://127.0.0.1:8533/?fixture_checkout=1');
  await page.getByText('Previewing: Fixture Collector · latest abandoned checkout',{exact:true}).waitFor();
  const main=page.locator('.st-key-crm-composer-preview').frameLocator('iframe[data-testid="stIFrame"]');
  await main.locator('.sc-cart-variant').first().waitFor();
  assert.equal(await main.locator('.sc-cart-variant').first().evaluate(e=>getComputedStyle(e).color),'rgb(255, 255, 255)');
  await page.getByRole('tab',{name:'Templates',exact:true}).click();
  await page.locator('[class*="_checkout_template_edit"] button').click();
  let dialog=page.getByRole('dialog');const source=dialog.getByRole('textbox',{name:'Master template HTML / CSS'});
  const original=await source.inputValue();
  const changed=original.replace('.sc-cart-variant { color:#ffffff;', '.sc-cart-variant { color:#d1a938 !important;').replace('.sc-cart-title { color:#ffffff;', '.sc-cart-title { color:#ff0000 !important;').replace('background:#d1a938;', 'background:#c59b2d !important;');
  await source.fill(changed);await source.press('Tab');
  const preview=dialog.locator('.st-key-crm-checkout-master-preview').frameLocator('iframe[data-testid="stIFrame"]');
  await preview.locator('.sc-cart-variant').first().waitFor();
  await page.waitForTimeout(350);
  assert.equal(await preview.locator('.sc-cart-variant').first().evaluate(e=>getComputedStyle(e).color),'rgb(209, 169, 56)');
  assert.equal(await preview.locator('.sc-cart-title').first().evaluate(e=>getComputedStyle(e).color),'rgb(255, 0, 0)');
  await dialog.getByRole('button',{name:'Save template',exact:true}).click();
  await dialog.waitFor({state:'hidden'});
  assert.equal(await main.locator('.sc-cart-variant').first().evaluate(e=>getComputedStyle(e).color),'rgb(255, 255, 255)');
  await page.getByRole('button',{name:'Use',exact:true}).first().click();
  await page.waitForTimeout(500);
  assert.equal(await main.locator('.sc-cart-variant').first().evaluate(e=>getComputedStyle(e).color),'rgb(209, 169, 56)');
  assert.equal(await main.locator('.sc-cart-button').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(197, 155, 45)');
  for(const width of [600,430,390,375,320]){
   const frame=await (await page.locator('.st-key-crm-composer-preview iframe[data-testid="stIFrame"]').elementHandle()).contentFrame();
   await frame.evaluate(w=>frameElement.style.width=w+'px',width);
   assert.ok(await main.locator('body').evaluate(()=>document.documentElement.scrollWidth)<=width+2);
  }
  await page.locator('[class*="_checkout_template_edit"] button').click();
  dialog=page.getByRole('dialog');assert.equal(await dialog.getByRole('textbox',{name:'Master template HTML / CSS'}).inputValue(),changed);
  await dialog.getByRole('button',{name:'Reset to default',exact:true}).click();
  await page.waitForTimeout(300);
  assert.equal(await dialog.getByRole('textbox',{name:'Master template HTML / CSS'}).inputValue(),original);
  await dialog.getByRole('button',{name:'Save template',exact:true}).click();await dialog.waitFor({state:'hidden'});
  await page.screenshot({path:'docs/performance-evidence/checkout-template-styles.png',fullPage:true});
  assert.equal(await page.getByTestId('stException').count(),0);
  console.log('Master edit preview, Save, Use, draft independence, Reset and responsive colour contract passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
