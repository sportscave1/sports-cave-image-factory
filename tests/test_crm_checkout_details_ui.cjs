// Render real production markup locally. No Shopify, database or email transport.
const {chromium}=require('playwright');
const {execFileSync}=require('node:child_process');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const html=execFileSync('.venv/Scripts/python.exe',['-c',`
from crm_abandoned_checkout import context,hydrate
from crm_campaign_content import render_campaign
from tests.test_crm_abandoned_checkout import checkout,native_document
from tests.test_crm_send_flow import CFG
c=checkout(currency='USD');line=c['lineItems']['nodes'][0]
line['title']='Mattingly, Jeter & Judge — The Captains'
line['variantTitle']='Black / XL - 62 × 87 cm (24.4 × 34.3 in)'
line['discountedTotalPriceWithCodeDiscount']['presentmentMoney']['amount']='423.30'
d=context(c);d['items'][0]['edition']={'limit':100,'next':52,'remaining':51}
print(render_campaign(hydrate(native_document(),d),CFG)['html'])
`],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage();
  await page.route('**/*',r=>r.request().url()==='https://cdn.shopify.com/fixture.png'
   ?r.fulfill({contentType:'image/png',body:fs.readFileSync('tests/fixtures/checkout_product_generated.png')}):r.abort());
  for(const width of [600,430,390,375,320]){
   await page.setViewportSize({width,height:900});await page.setContent(html);
   await page.locator('.sc-cart-image').waitFor();
   await page.locator('.sc-cart-image').evaluate(img=>img.decode());
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth)<=width);
   assert.equal(await page.locator('.sc-cart-variant').textContent(),'Black Frame · XL');
   assert.equal(await page.locator('.sc-cart-dimensions').textContent(),'62 × 87 cm (24.4 × 34.3 in)');
   assert.equal(await page.locator('.sc-cart-price').textContent(),'US$423.30');
   assert.equal(await page.locator('.sc-cart-qty').textContent(),'Qty 2');
   assert.equal(await page.locator('.sc-cart-variant').evaluate(e=>getComputedStyle(e).color),'rgb(183, 147, 53)');
   assert.ok(await page.locator('.sc-cart-image').evaluate(e=>Math.abs(e.width/e.height-e.naturalWidth/e.naturalHeight)<0.01));
   assert.ok(await page.locator('.sc-cart-button').evaluate(e=>e.getBoundingClientRect().right)<=width);
   const positions=await page.locator('.sc-cart-meta span').evaluateAll(es=>es.map(e=>e.getBoundingClientRect().top));
   assert.ok(Math.max(...positions)-Math.min(...positions)<5,'Qty/price stay on one row');
  }
  console.log('Checkout details: 600/430/390/375/320px, aspect ratio, one-row Qty/price, gold variant and CTA containment passed');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
