const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
test('title and below-fold totals refresh together from OS on every page load',async()=>{
 const {chromium}=require(process.env.REVIEW_PLAYWRIGHT_MODULE);
 const browser=await chromium.launch({channel:process.env.REVIEW_BROWSER_CHANNEL||'msedge',headless:true});
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
   await page.addScriptTag({content:fs.readFileSync(process.env.REVIEW_COUNT_WIDGET_SOURCE||'shopify/reviews/live-review-widget.js','utf8')});
   await page.waitForFunction(n=>document.querySelector('.scx-review-text span').textContent===`${n} reviews`,expected);
   assert.match(await page.locator('[data-review-summary]').textContent(),new RegExp(expected+' reviews'));
   assert.equal(await page.locator('[data-review-archive] > *').count(),0);
  }
  assert.equal(calls,2);
 } finally {await browser.close()}
});

test('published counts and stars stay in sync across refresh, older pages, errors and section replacement',async()=>{
 const {chromium}=require(process.env.REVIEW_PLAYWRIGHT_MODULE);
 const browser=await chromium.launch({channel:process.env.REVIEW_BROWSER_CHANNEL||'msedge',headless:true});
 try {
  const page=await browser.newPage();let total=211,average=4.82,revision=1,calls=0,fail=false;
  await page.clock.install({time:new Date('2026-11-27T04:00:00Z')});
  const snapshot=()=>({summary:{count:total,average},histogram:[[5,total],[4,0],[3,0],[2,0],[1,0]],as_of:`2026-11-27T04:00:${String(revision).padStart(2,'0')}Z`});
  await page.route('**/*',route=>{
   const url=new URL(route.request().url());
   if(!url.pathname.includes('/reviews/widget'))return route.abort();
   calls++;
   if(fail&&url.searchParams.get('summary')==='1')return route.fulfill({status:503,headers:{'Access-Control-Allow-Origin':'*'}});
   return route.fulfill({json:{reviews:[],featured:[],next_offset:null,...snapshot()},headers:{'Access-Control-Allow-Origin':'*'}});
  });
  const original=fs.readFileSync('tests/test_existing_reviews_widget.cjs','utf8'),prefix="await page.evaluate(()=>{document.body.insertAdjacentHTML('beforeend',`";
  const html=original.split(prefix)[1].split('`)});')[0];
  const header='<button class="scx-review-inline" aria-busy="true"><span class="scx-stars">★★★★★</span><span class="scx-review-text"><strong>—</strong><span>•</span><span>— reviews</span></span></button>';
  await page.setContent(header+header+'<div style="height:6000px"></div>'+html+html);
  await page.addScriptTag({content:fs.readFileSync(process.env.REVIEW_COUNT_WIDGET_SOURCE||'shopify/reviews/live-review-widget.js','utf8')});
  await page.waitForFunction(()=>document.querySelector('.scx-review-text span:last-child').textContent==='211 reviews');
  assert.equal(calls,1,'one shared initial feed, even with two widgets');
  total=212;average=4.25;revision=2;
  await page.clock.fastForward(30001);
  await page.waitForFunction(()=>document.querySelector('.scx-review-text span:last-child').textContent==='212 reviews');
  assert.deepEqual(await page.locator('.scx-review-text strong').allTextContents(),['4.3','4.3']);
  for(const text of await page.locator('[data-review-summary]').allTextContents())assert.match(text,/4.25 \/ 5.*212 reviews/);
  assert.match(await page.locator('.scx-stars').first().getAttribute('style'),/85%/);
  assert.equal(calls,2,'only one lightweight refresh');
  // A delayed page loaded from an older cache cannot roll the totals back.
  await page.evaluate(()=>document.querySelector('sc-customer-reviews').nativeApply({reviews:[],featured:[],next_offset:null,summary:{count:209,average:4.82},histogram:[[5,183],[4,20],[3,2],[2,2],[1,2]],as_of:'2026-11-27T04:00:01Z'}));
  assert.equal(await page.locator('.scx-review-text span:last-child').first().textContent(),'212 reviews');
  fail=true;await page.clock.fastForward(30001);
  assert.equal(await page.locator('.scx-review-text span:last-child').first().textContent(),'212 reviews','failure retains last good count');
  fail=false;total=213;average=4.4;revision=3;
  await page.clock.fastForward(60001);
  await page.waitForFunction(()=>document.querySelector('.scx-review-text span:last-child').textContent==='213 reviews');
  // Invalid payloads never turn a known rating into zero or NaN.
  await page.evaluate(()=>document.querySelector('sc-customer-reviews').nativeSummary({count:-1,average:null},'2026-11-27T04:00:04Z'));
  assert.equal(await page.locator('.scx-review-text span:last-child').first().textContent(),'213 reviews');
  await page.evaluate(()=>{document.querySelector('.scx-review-text strong').textContent='—';document.dispatchEvent(new Event('shopify:section:load'))});
  assert.equal(await page.locator('.scx-review-text strong').first().textContent(),'4.4');
  // Newer moderation snapshots may legitimately decrease published totals.
  await page.evaluate(()=>document.querySelector('sc-customer-reviews').nativeSummary({count:212,average:4.5},'2026-11-27T04:00:05Z'));
  assert.equal(await page.locator('.scx-review-text span:last-child').first().textContent(),'212 reviews');
  await page.evaluate(()=>window.dispatchEvent(new Event('pagehide')));
  const paused=calls;await page.clock.fastForward(120001);assert.equal(calls,paused,'no polling after pagehide');
  total=214;average=4.6;revision=6;
  await page.evaluate(()=>window.dispatchEvent(new Event('pageshow')));
  await page.waitForFunction(()=>document.querySelector('.scx-review-text span:last-child').textContent==='214 reviews');
 } finally {await browser.close()}
});
