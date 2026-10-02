// Local-only OS preview and real widget assets, no provider requests or live data.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ROOT=path.resolve(__dirname,'..');
const EXT=path.join(ROOT,'shopify_customer_account/extensions/sports-cave-reviews');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext();
 await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage();
 const evidence=path.join(ROOT,'docs/performance-evidence/reviews');fs.mkdirSync(evidence,{recursive:true});
 try{
  for(const [width,height] of [[1920,1080],[1366,768],[750,900],[430,900],[390,844],[375,812],[320,740]]){
   await page.setViewportSize({width,height});await page.goto('http://127.0.0.1:8541');
   await page.locator('.rv-row').first().waitFor();assert.equal(await page.getByTestId('stException').count(),0);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'OS overflow '+width);
   await page.waitForFunction(()=>{const main=document.querySelector('[data-testid=stMain]');return main.scrollWidth<=main.clientWidth+1},null,{timeout:10000});
   if(width<=430)assert(await page.locator('.st-key-reviews-filters [data-testid=stSelectbox]').first().evaluate(e=>e.getBoundingClientRect().width>=110),'Readable mobile filter');
   assert.equal(await page.locator('.sc-home-kpi').count(),5);
   assert.equal(await page.locator('.st-key-reviews-tabs button').count(),3);
   await page.screenshot({path:path.join(evidence,'overview-'+width+'.png'),fullPage:true});
  }
  await page.setViewportSize({width:1366,height:768});await page.goto('http://127.0.0.1:8541');await page.locator('.rv-row').first().waitFor();
  await page.getByRole('button',{name:/Open$/}).first().click();await page.getByRole('dialog').waitFor();
  assert.equal(await page.getByTestId('stException').count(),0);assert.equal(await page.getByRole('button',{name:'Save reply',exact:true}).count(),1);
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Display',exact:true}).click();await page.getByText('Shopify display',{exact:true}).waitFor();
  assert.equal(await page.getByTestId('stException').count(),0);
  await page.getByRole('button',{name:'Import reviews',exact:true}).click();await page.getByText('Connected sources',{exact:true}).waitFor();
  assert.equal(await page.getByTestId('stException').count(),0);
  const js=fs.readFileSync(path.join(EXT,'assets/reviews.js'),'utf8');const css=fs.readFileSync(path.join(EXT,'assets/reviews.css'),'utf8');
  const review={id:'fixture',product_title:'63 Years Later: Ryan Fox Open Championship Wall Art',product_url:'https://fixture.example/products/fox',product_image:'',reviewer_name:'Fixture Collector',rating:4,title:'<img src=x onerror=alert(1)>',body:'Beautiful collector artwork.',created_at:'2026-10-01',verified_purchase:false,merchant_reply:'Thank you.'};
  for(const width of [600,430,390,375,320]){
   await page.setViewportSize({width,height:800});await page.goto('http://127.0.0.1:8541');
   await page.setContent('<style>body{margin:16px;font:16px system-ui}'+css+'</style><sports-cave-reviews data-mode="all" data-endpoint="https://reviews.fixture/reviews/public"><h2>Sports Cave Reviews</h2><p data-summary></p><div data-controls></div><div data-list></div><p data-error></p><button data-more hidden>Load more</button></sports-cave-reviews>');
   let calls=0;
   await page.route('https://reviews.fixture/**',async route=>{
    calls++;const u=new URL(route.request().url());assert.equal(u.searchParams.get('sort'),calls===1?null:'highest');await route.fulfill({json:{summary:{average:4,count:2},reviews:[review],products:[{product_id:'gid://shopify/Product/55',product_title:review.product_title}],next_offset:u.searchParams.get('offset')==='0'?1:null,appearance:{accent:'#b99232',density:'compact',sort:'highest'}}});
   });
   await page.addScriptTag({content:js});await page.locator('sports-cave-reviews article').waitFor();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'Widget overflow '+width);
   assert.equal(await page.locator('sports-cave-reviews article img').count(),0,'Untrusted title cannot become HTML');
   assert.equal(await page.getByText('Verified purchase',{exact:false}).count(),0);
   assert.equal(await page.getByRole('combobox',{name:'Sort reviews'}).inputValue(),'highest','Configured default sort');
   await page.getByRole('button',{name:'Load more'}).click();await page.waitForFunction(()=>document.querySelectorAll('sports-cave-reviews article').length===2);
   assert.equal(calls,2,'Bounded load-more requests');await page.screenshot({path:path.join(evidence,'storefront-'+width+'.png'),fullPage:true});
   await page.unroute('https://reviews.fixture/**');
  }
  // Product and star blocks share the same product key and stable anchor.
  await page.goto('http://127.0.0.1:8541');
  await page.setContent('<style>'+css+'</style><sports-cave-reviews data-mode="stars" data-product="55" data-endpoint="https://reviews.fixture/reviews/public"><a href="#sc-product-reviews-55" data-summary>Customer reviews</a><span data-error></span></sports-cave-reviews><sports-cave-reviews id="sc-product-reviews-55" data-mode="product" data-product="55" data-endpoint="https://reviews.fixture/reviews/public"><p data-summary></p><div data-controls></div><div data-list></div><p data-error></p><button data-more hidden>Load more</button></sports-cave-reviews>');
  const queries=[];let fail=false;
  await page.route('https://reviews.fixture/**',async route=>{
   const u=new URL(route.request().url());queries.push(u.searchParams);assert.equal(u.searchParams.get('product'),'55');
   if(fail){await route.fulfill({status:503});return}
   await route.fulfill({json:{summary:{average:4.5,count:2},reviews:u.searchParams.get('summary')==='1'?[]:[review],products:[],next_offset:null,appearance:{accent:'#b99232'}}});
  });
  await page.addScriptTag({content:js});await page.locator('sports-cave-reviews article').waitFor();
  assert.equal(await page.locator('[data-mode=stars] a').getAttribute('href'),'#sc-product-reviews-55');
  assert(queries.some(q=>q.get('summary')==='1'));assert.equal(await page.locator('[data-mode=product] [data-summary]').textContent(),'★★★★★ 4.5 · 2 reviews');
  fail=true;await page.locator('[data-mode=product] select').first().selectOption('highest');await page.getByRole('button',{name:'Retry',exact:true}).waitFor();
  assert.equal(await page.locator('[data-mode=product] article').count(),1,'Refresh error retains resolved reviews');
  assert.equal(await page.locator('[data-mode=product] [data-summary]').textContent(),'★★★★★ 4.5 · 2 reviews');
  console.log('Reviews UI: 7 OS widths, 5 storefront widths, lazy tabs, escaping and pagination passed');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
