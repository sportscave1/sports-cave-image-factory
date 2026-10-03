// Synthetic loopback fixture. No customer data or external requests.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {execFileSync}=require('node:child_process');
execFileSync(path.resolve('.venv/Scripts/python.exe'),['-c',"from tests.test_crm_abandoned_checkout import *; Path('tests/fixtures/checkout_email_generated.html').write_text(render_campaign(hydrate(native_document(),context(checkout(items=2))),CFG)['html'],encoding='utf-8')"],{env:{...process.env,PYTHONUTF8:'1'}});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext();
  await context.route('**/*',r=>{
   const u=new URL(r.request().url());
   if(u.hostname==='127.0.0.1')return r.continue();
   if(u.href==='https://cdn.shopify.com/fixture.png')return r.fulfill({contentType:'image/png',body:fs.readFileSync('tests/fixtures/checkout_product_generated.png')});
   return r.abort();
  });
  const page=await context.newPage();await page.goto('http://127.0.0.1:8533/?fixture_checkout=1');
  await page.getByRole('button',{name:'Live preview',exact:true}).waitFor();
  await page.getByText('Previewing: Fixture Collector · latest abandoned checkout',{exact:true}).waitFor();
  assert.equal(await page.getByTestId('stException').count(),0);
  assert.equal(await page.getByText(/Auto fill/i).count(),0);
  await page.getByRole('tab',{name:'Templates',exact:true}).click();
  await page.getByRole('button',{name:'Use Abandoned Checkout template',exact:true}).click();
  await page.getByText('Previewing: Fixture Collector · latest abandoned checkout',{exact:true}).waitFor();
  for(const tab of ['Editor','Settings']){
   await page.getByRole('tab',{name:tab,exact:true}).click();
   assert.equal(await page.getByText(/Auto fill/i).count(),0);
  }
  await page.getByRole('tab',{name:'Editor',exact:true}).click();
  await page.locator('iframe[src*="crm_middle_sections"]').waitFor();
  const section=page.frames().find(f=>f.url().includes('crm_middle_sections'));
  assert.ok(section);assert.equal(await section.getByText('Abandoned checkout products',{exact:true}).count(),1);
  for(const [width,height] of [[1920,1080],[1440,900],[1366,768],[1024,768],[768,900],[430,900],[390,844],[320,740]]){
   await page.setViewportSize({width,height});await page.waitForTimeout(150);
   const size=await page.evaluate(()=>document.documentElement.scrollWidth);
   assert.ok(size<=width+2,'Editor overflow '+width+': '+size);
   assert.equal(await page.getByTestId('stException').count(),0);
   await page.screenshot({path:path.resolve('docs/performance-evidence/checkout-editor-'+width+'.png'),fullPage:true});
   console.log('Checkout editor '+width+'px: contained; native block; no Auto Fill');
  }
  await page.setViewportSize({width:1366,height:768});await page.getByRole('button',{name:'Live preview',exact:true}).click();
  await page.getByRole('dialog').waitFor();
  await page.getByRole('dialog').getByText('Previewing: Fixture Collector · latest abandoned checkout',{exact:true}).waitFor();
  const email=page.getByRole('dialog').frameLocator('iframe[srcdoc]');
  await email.getByRole('link',{name:'Complete Your Order →'}).waitFor();
  assert.equal(await email.getByRole('link',{name:'Complete Your Order →'}).count(),1);
  assert.equal(await email.getByText('AUD 199.50',{exact:false}).count(),2);
  assert.equal(await email.getByText('CAMPAIGN TEST / PREVIEW · LIVE MARKETING DISABLED',{exact:true}).count(),0,'Live Preview uses production renderer');
  assert.equal(await page.getByTestId('stException').count(),0);
  await page.screenshot({path:path.resolve('docs/performance-evidence/checkout-live-preview.png'),fullPage:true});
  const html=fs.readFileSync('tests/fixtures/checkout_email_generated.html','utf8');
  for(const width of [600,430,390,375,360,320]){
   const view=await context.newPage();await view.setViewportSize({width,height:900});await view.setContent(html);
   assert.ok(await view.evaluate(()=>document.documentElement.scrollWidth)<=width+1,'Email overflow '+width);
   assert.equal(await view.getByRole('link',{name:'Complete Your Order →'}).count(),1);
   assert.equal(await view.locator('img').evaluateAll(images=>images.every(i=>getComputedStyle(i).objectFit!=='cover')),true);
   await view.locator('img').first().waitFor();
   await view.waitForFunction(()=>[...document.images].every(i=>i.complete&&i.naturalWidth>0));
   assert.ok(await view.locator('img').evaluateAll(images=>images.every(i=>Math.abs(i.width/i.height-i.naturalWidth/i.naturalHeight)<0.02)),'Image distortion '+width);
   await view.screenshot({path:path.resolve('docs/performance-evidence/checkout-email-'+width+'.png'),fullPage:true});
   await view.close();console.log('Final checkout email '+width+'px: contained; items and CTA visible');
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
