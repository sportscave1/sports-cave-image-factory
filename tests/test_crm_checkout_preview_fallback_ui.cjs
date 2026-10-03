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
   const page=await context.newPage();const entered=Date.now();await page.goto('http://127.0.0.1:8533/?fixture_checkout=1&fixture_legacy=1&fixture_profile=1'+(failure?'&fixture_failure=1':'&fixture_delay=1'));
   await page.getByRole('button',{name:'Save draft',exact:true}).waitFor();
   console.log('Editor shell ready: '+(Date.now()-entered)+'ms (local fixture)');
   assert.equal(await page.getByRole('button',{name:'Live preview',exact:true}).count(),0);
   await page.getByText('Legacy checkout block detected · preview uses native checkout products.',{exact:true}).waitFor();
   const expected=failure?'Previewing: Sample abandoned checkout':'Previewing: Fixture Collector · latest abandoned checkout';
   await page.getByText(expected,{exact:true}).waitFor();
   const email=page.locator('.st-key-crm-composer-preview').frameLocator('iframe[src*="crm_automation_stable_preview"]').frameLocator('iframe[srcdoc]');
   await email.getByRole('heading',{name:'MY CUSTOM HEADLINE'}).waitFor();
   await email.getByText('MY CUSTOM OUTRO',{exact:true}).waitFor();
   assert.equal(await email.getByText(/\{\{|\{%/).count(),0);
   assert.equal(await page.getByTestId('stException').count(),0);
   await page.frameLocator('iframe[src*="crm_automation_stable_size"]').getByText(/Email size .* KB/).waitFor();
   await page.getByRole('tab',{name:'Editor',exact:true}).click();
   const section=page.frameLocator('iframe[src*="crm_middle_sections"]');
   await section.getByRole('button',{name:'Edit HTML Section 1',exact:true}).waitFor();
   await section.getByRole('button',{name:'Edit HTML Section 2',exact:true}).waitFor();
   for(const width of [1366,768,390,320]){
    await page.setViewportSize({width,height:900});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth)<=width+2);
   }
   await page.setViewportSize({width:1366,height:768});
   const component=page.locator('.st-key-crm-composer-preview iframe[src*="crm_automation_stable_preview"]');
   const frame=await (await component.elementHandle()).contentFrame();
   const initial=await frame.evaluate(()=>({updates:window.previewUpdates,loads:window.previewLoads}));
   if(!failure){
    await email.locator('body').evaluate(()=>window.scrollTo(0,200));
    const idleScroll=await email.locator('body').evaluate(()=>window.scrollY);
    await page.waitForTimeout(60000);
    assert.deepEqual(await frame.evaluate(()=>({updates:window.previewUpdates,loads:window.previewLoads})),initial);
    assert.equal(await email.locator('body').evaluate(()=>window.scrollY),idleScroll);
    console.log('60s idle: zero updates, reloads and scroll resets');
   }
   await page.locator('.st-key-crm-preview-devices button:visible').nth(1).click();
   await frame.waitForFunction(()=>document.getElementById('email').style.width==='390px');
   await page.locator('.st-key-crm-preview-devices button:visible').nth(0).click();
   await frame.waitForFunction(()=>document.getElementById('email').style.width==='600px');
   assert.deepEqual(await frame.evaluate(()=>({updates:window.previewUpdates,loads:window.previewLoads})),initial);
   for(const width of [320,360,375,390,430,600]){
    await frame.evaluate(w=>document.getElementById('email').style.width=w+'px',width);
    assert.ok(await email.locator('body').evaluate(()=>document.documentElement.scrollWidth)<=width+2);
    assert.ok(await email.getByRole('link',{name:'Complete Your Order →',exact:true}).count() || failure);
   }
   await frame.evaluate(()=>document.getElementById('email').style.width='600px');
   if(!failure){
    const area=section.getByRole('textbox',{name:'HTML Section 1 HTML',exact:true});
    if(!await area.isVisible())await section.getByRole('button',{name:'Edit HTML Section 1',exact:true}).click();
    await area.focus();await area.press('Control+End');
    const started=Date.now();
    await area.pressSequentially('abcdefghijklmnopqrst',{delay:15});
    await frame.waitForFunction(n=>window.previewUpdates===n+1,initial.updates);
    await page.waitForTimeout(700);
    assert.equal(await frame.evaluate(()=>window.previewUpdates),initial.updates+1);
    console.log('20 characters: one preview update, '+(Date.now()-started)+'ms including typing/settle');
    await page.getByRole('button',{name:'Save draft',exact:true}).click();
    await page.getByText('Fixture Shopify requests: 1',{exact:true}).waitFor();
    assert.equal(await frame.evaluate(()=>window.previewUpdates),initial.updates+1);
   }
   for(const width of [1920,1600,1440,1366,1280,1024]){
    await page.setViewportSize({width,height:900});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth)<=width+2);
   }
   assert.equal(await page.getByTestId('stException').count(),0);
   await page.screenshot({path:path.resolve('docs/performance-evidence/checkout-fallback-'+(failure?'sample':'real')+'.png'),fullPage:true});
   console.log('Legacy checkout '+(failure?'provider failure/sample':'real')+': embedded live preview stable; sections retained; size resolved; responsive');
   await context.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
