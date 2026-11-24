const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
test('title and below-fold totals refresh together from OS on every page load',async()=>{
 const {chromium}=require(process.env.REVIEW_PLAYWRIGHT_MODULE);
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:390,height:844}});let total=209,calls=0;
  await page.route('**/reviews/widget?**',route=>{calls++;return route.fulfill({json:{reviews:[],featured:[],summary:{count:total,average:4.82},histogram:[],next_offset:null},headers:{'Access-Control-Allow-Origin':'*'}})});
  const original=fs.readFileSync('tests/test_existing_reviews_widget.cjs','utf8');
  const prefix="await page.evaluate(()=>{document.body.insertAdjacentHTML('beforeend',`";
  const html=original.split(prefix)[1].split('`)});')[0];
  for (const expected of [209,210]) {
   total=expected;
   await page.goto('about:blank');
   await page.setContent('<div class="scx-review-text"><strong>4.8</strong><span>209 reviews</span></div><div style="height:6000px"></div>'+html);
   await page.addScriptTag({content:fs.readFileSync('shopify/reviews/live-review-widget.js','utf8')});
   await page.waitForFunction(n=>document.querySelector('.scx-review-text span').textContent===`${n} reviews`,expected);
   assert.match(await page.locator('[data-review-summary]').textContent(),new RegExp(expected+' reviews'));
   assert.equal(await page.locator('[data-review-archive] > *').count(),0);
  }
  assert.equal(calls,2);
 } finally {await browser.close()}
});
