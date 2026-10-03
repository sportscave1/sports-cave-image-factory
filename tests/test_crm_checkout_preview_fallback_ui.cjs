// Synthetic loopback only; no email submission or external assets.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  for(const failure of [false,true]){
   const context=await browser.newContext();
   await context.route('**/*',r=>{
    const u=new URL(r.request().url());
    if(u.hostname==='127.0.0.1')return r.continue();
    if(u.href==='https://cdn.shopify.com/fixture.png')return r.fulfill({contentType:'image/png',body:fs.readFileSync('tests/fixtures/checkout_product_generated.png')});
    return r.abort();
   });
   const page=await context.newPage();await page.goto('http://127.0.0.1:8533/?fixture_checkout=1&fixture_legacy=1'+(failure?'&fixture_failure=1':''));
   await page.getByRole('button',{name:'Live preview',exact:true}).waitFor();
   await page.getByText('Legacy checkout block detected · preview uses native checkout products.',{exact:true}).waitFor();
   const expected=failure?'Previewing: Sample abandoned checkout':'Previewing: Fixture Collector · latest abandoned checkout';
   await page.getByText(expected,{exact:true}).waitFor();
   const email=page.locator('.st-key-crm-composer-preview').frameLocator('iframe[srcdoc]');
   await email.getByRole('heading',{name:'MY CUSTOM HEADLINE'}).waitFor();
   await email.getByText('MY CUSTOM OUTRO',{exact:true}).waitFor();
   assert.equal(await email.getByText(/\{\{|\{%/).count(),0);
   assert.equal(await page.getByTestId('stException').count(),0);
   await page.waitForFunction(()=>[...document.querySelectorAll('.sc-email-size')].some(e=>e.textContent.includes('KB')));
   await page.getByRole('tab',{name:'Editor',exact:true}).click();
   const section=page.frameLocator('iframe[src*="crm_middle_sections"]');
   await section.getByRole('button',{name:'Edit HTML Section 1',exact:true}).waitFor();
   await section.getByRole('button',{name:'Edit HTML Section 2',exact:true}).waitFor();
   for(const width of [1366,768,390,320]){
    await page.setViewportSize({width,height:900});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth)<=width+2);
   }
   await page.setViewportSize({width:1366,height:768});
   await page.getByRole('button',{name:'Live preview',exact:true}).click();
   const dialog=page.getByRole('dialog');await dialog.getByText(expected,{exact:true}).waitFor();
   const live=dialog.frameLocator('iframe[srcdoc]');await live.getByRole('heading',{name:'MY CUSTOM HEADLINE'}).waitFor();
   await live.getByText('MY CUSTOM OUTRO',{exact:true}).waitFor();
   await dialog.locator('.st-key-crm-live-preview-devices button:visible').nth(1).click();
   await page.waitForFunction(()=>Math.abs(document.querySelector('[role="dialog"] iframe[srcdoc]')?.getBoundingClientRect().width-390)<2);
   await live.getByRole('heading',{name:'MY CUSTOM HEADLINE'}).waitFor();
   await dialog.locator('.st-key-crm-live-preview-devices button:visible').nth(0).click();
   await page.waitForFunction(()=>Math.abs(document.querySelector('[role="dialog"] iframe[srcdoc]')?.getBoundingClientRect().width-600)<2);
   assert.equal(await page.getByTestId('stException').count(),0);
   await page.screenshot({path:path.resolve('docs/performance-evidence/checkout-fallback-'+(failure?'sample':'real')+'.png'),fullPage:true});
   console.log('Legacy checkout '+(failure?'provider failure/sample':'real')+': editor and Live Preview visible; sections retained; size resolved; responsive');
   await context.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
