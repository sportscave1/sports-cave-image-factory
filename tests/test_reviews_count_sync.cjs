const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const source=()=>fs.readFileSync(process.env.REVIEW_COUNT_WIDGET_SOURCE||'shopify/reviews/live-review-widget.js','utf8');
const release='shopify/reviews/releases/20261127-instant-mirror';
const header='<button class="scx-review-inline"><span class="scx-stars">★★★★★</span><span class="scx-review-text"><strong>4.8</strong><span>•</span><span>211 reviews</span></span></button>';
function fixture(){
 const original=fs.readFileSync('tests/test_existing_reviews_widget.cjs','utf8');
 const html=original.split("await page.evaluate(()=>{document.body.insertAdjacentHTML('beforeend',`")[1].split('`)});')[0];
 const summary=fs.readFileSync(release+'/snippets/sc-review-os-header.liquid','utf8').match(/<p class="sc-reviews__summary"[\s\S]*?<\/p>/)[0];
 return header+'<div style="height:6000px"></div>'+html.replace(/<p[^>]*data-review-summary[\s\S]*?<\/p>/,summary);
}
test('original header style and instant totals are restored without placeholders or poller',()=>{
 const before=require('node:child_process').execFileSync('git',['show','0355b418:shopify/reviews/production-cleanup/snippets/sc-product-titlebar.liquid'],{encoding:'utf8'}).replaceAll('\r\n','\n').replace('scx_review_count = 209','scx_review_count = 211');
 assert.equal(fs.readFileSync(release+'/snippets/sc-product-titlebar.liquid','utf8').replaceAll('\r\n','\n'),before);
 assert.doesNotMatch(source(),/summary=1|OS_REVIEW_SUMMARY_SYNC_V1|osSummarySync/);
 assert.doesNotMatch(fs.readFileSync(release+'/snippets/sc-review-os-header.liquid','utf8'),/—|aria-busy/);
});
for(const offline of [false,true])test(`instant header mirrors bottom with ${offline?'unavailable':'slow'} provider, no eager requests or polling`,async()=>{
 const {chromium}=require(process.env.REVIEW_PLAYWRIGHT_MODULE);
 const browser=await chromium.launch({channel:process.env.REVIEW_BROWSER_CHANNEL||'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});let calls=0,releaseResponse;
  await page.clock.install();
  await page.route('**/*',async route=>{
   if(!route.request().url().includes('/reviews/widget'))return route.abort();
   calls++;await new Promise(resolve=>releaseResponse=resolve);
   if(offline)return route.fulfill({status:503,headers:{'Access-Control-Allow-Origin':'*'}});
   return route.fulfill({json:{summary:{count:212,average:4.75},reviews:[],featured:[],histogram:[],next_offset:null},headers:{'Access-Control-Allow-Origin':'*'}});
  });
  await page.setContent(fixture());
  const top=page.locator('.scx-review-text');
  assert.match(await top.innerText(),/211 reviews/,'initial HTML already has its total');
  await page.addScriptTag({content:source()});
  await page.clock.runFor(100);
  assert.equal(calls,0,'header never requests OS data');
  await page.evaluate(()=>document.querySelector('sc-customer-reviews').scrollIntoView());
  await page.waitForFunction(()=>document.querySelector('sc-customer-reviews').hasAttribute('aria-busy'));
  await page.clock.runFor(100);
  assert.equal(calls,1,'bottom widget owns one request');
  assert.match(await top.innerText(),/211 reviews/,'slow request cannot blank header');
  releaseResponse();
  await page.waitForFunction(()=>!document.querySelector('sc-customer-reviews').hasAttribute('aria-busy'));
  assert.match(await top.innerText(),offline?/211 reviews/:/212 reviews/);
  if(!offline)assert.equal(await page.locator('.scx-review-text strong').textContent(),'4.8');
  await page.clock.fastForward(300001);
  assert.equal(calls,1,'no summary polls or independent requests');
  // Any normal bottom-summary update is mirrored without fetching anything.
  await page.evaluate(()=>document.querySelector('sc-customer-reviews').summary('4.60','213'));
  assert.match(await top.innerText(),/213 reviews/);assert.equal(await page.locator('.scx-review-text strong').textContent(),'4.6');
  assert.equal(await page.locator('.scx-stars').getAttribute('style'),null,'original stars are untouched');
  assert.equal(calls,1);
 }finally{await browser.close()}
});
