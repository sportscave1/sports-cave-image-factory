// Static widget acceptance only: synthetic media, mocked API, no OS server or live data.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.REVIEW_PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..');
test('review video remains a small poster until opened, with bounded mobile playback',async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage();
 page.on('pageerror',error=>console.error('Widget error:',error.message));
 page.on('console',message=>{if(message.type()==='error')console.error('Browser:',message.text())});
 let videoRequests=0;
 const media='/reviews/media/00000000-0000-0000-0000-000000000001';
 const tiny=fs.readFileSync(path.join(root,'.tmp-reviews-browser/fixture.webp'));
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.hostname!=='reviews.fixture')return route.abort();
  if(url.pathname==='/reviews/public')return route.fulfill({headers:{'Access-Control-Allow-Origin':'*'},json:{summary:{count:1,average:5},products:[],next_offset:null,reviews:[{rating:5,title:'Synthetic review',body:'Looks great.',reviewer_name:'Fixture',media:[{kind:'video',url:'https://reviews.fixture'+media+'?size=original',thumbnail_url:'https://reviews.fixture'+media+'?size=320',poster_url:'https://reviews.fixture'+media+'?size=1280'},{kind:'image',url:'https://reviews.fixture'+media+'?size=1280',thumbnail_url:'https://reviews.fixture'+media+'?size=320'},{kind:'image',url:'https://private.example/blocked',thumbnail_url:'https://private.example/blocked'}]}]}});
  if(url.pathname===media){if(url.searchParams.get('size')==='original'){videoRequests++;return route.fulfill({status:200,body:'',contentType:'video/mp4'})}return route.fulfill({body:tiny,contentType:'image/webp'})}
  return route.abort();
 });
 try{
  for(const width of [1440,390,320]){
   await page.setViewportSize({width,height:800});
   await page.setContent('<style>body{margin:12px;font:16px Arial}'+fs.readFileSync(path.join(root,'shopify_customer_account/extensions/sports-cave-reviews/assets/reviews.css'),'utf8')+'</style><sports-cave-reviews data-mode="product" data-endpoint="https://reviews.fixture/reviews/public"><p data-summary></p><div data-controls></div><div data-list></div><p data-error></p><button data-more hidden>More</button></sports-cave-reviews>');
   await page.addScriptTag({content:fs.readFileSync(path.join(root,'shopify_customer_account/extensions/sports-cave-reviews/assets/reviews.js'),'utf8')});
   await page.getByRole('button',{name:'Play customer review video'}).waitFor({timeout:5000}).catch(async error=>{console.error((await page.content()).slice(-3500));throw error});
   assert.equal(await page.locator('.sc-review-media-button').count(),2,'Foreign media is rejected');
   assert.equal(await page.locator('video').count(),0);assert.equal(videoRequests,0);
   assert.equal(await page.locator('.sc-review-media-button img').first().getAttribute('loading'),'lazy');
   assert.equal((await page.locator('.sc-review-media-button').first().boundingBox()).height,96);
   await page.getByRole('button',{name:'Play customer review video'}).click();
   const video=page.locator('dialog video');assert.equal(await video.getAttribute('preload'),'none');
   assert.equal(await video.getAttribute('autoplay'),null);assert.equal(await video.getAttribute('controls'),'');
   const bounds=await video.boundingBox();assert.ok(bounds.width<=width-24);assert.ok(bounds.height<=576);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   await page.getByRole('button',{name:'Close',exact:true}).click();await page.locator('dialog').waitFor({state:'detached'});
   await page.getByRole('button',{name:'Open customer review photo'}).click();
   assert.ok((await page.locator('dialog img').getAttribute('src')).endsWith('size=1280'));
   await page.keyboard.press('Escape');await page.locator('dialog').waitFor({state:'detached'});
  }
 }finally{await browser.close()}
});
