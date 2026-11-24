const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const enabled=Boolean(process.env.REVIEW_DRAFT_WIDGET_SOURCE&&process.env.REVIEW_PLAYWRIGHT_MODULE);
for(const country of ['AU','US'])test(`draft ${country}: one initial request, stable country cards and recoverable pagination`,{skip:!enabled},async()=>{
 const {chromium}=require(process.env.REVIEW_PLAYWRIGHT_MODULE),browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}}),requests=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));let failMore=true;
  const ids=['f0a533af-ce9f-4114-845d-dc003032c337','d69b0463-04bc-412c-948a-1636353b3528','4c91276a-636b-4eae-944a-d9912d65900e','013c8326-eeb9-41c0-8a3a-07ee648bcf2a'];
  const row=(id,index)=>({id:'fixture-'+index,legacy_id:id,reviewer_name:'Fixture '+index,title:'Synthetic edition',body:'Synthetic review body for testing',rating:5,media:[{kind:'image',url:'https://sports-cave-image-factory.onrender.com/reviews/media/aaaa?size=1280',thumbnail_url:'https://sports-cave-image-factory.onrender.com/reviews/media/aaaa?size=320',carousel_url:'https://sports-cave-image-factory.onrender.com/reviews/media/aaaa?size=640'}]});
  const featured=ids.map(row),archive=Array.from({length:5},(_,i)=>row(ids[0],i+10));archive[0].created_at='2026-01-02T00:00:00+00:00';archive[0].source_verified=true;archive[1].media=[];archive[1].shop_verified=true;archive[1].product_thumbnail_url='https://cdn.shopify.com/s/files/black-frame.jpg?width=136&format=webp';archive[1].product_url='https://www.sportscaveshop.com/products/fixture';archive[2].media[0].kind='video';archive[2].media[0].url='https://sports-cave-image-factory.onrender.com/reviews/media/aaaa?size=original';
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());
   if(url.hostname==='fixture.example')return route.fulfill({contentType:'text/html',body:'<!doctype html><html></html>'});
   if(url.pathname==='/reviews/widget'){
    requests.push(url.href);assert.equal(url.searchParams.get('country'),country);
    if(url.searchParams.get('offset')==='5'&&failMore)return route.fulfill({status:503});
    return route.fulfill({json:{featured:url.searchParams.get('offset')==='0'?featured:[],reviews:url.searchParams.get('offset')==='0'?archive:[row(ids[1],15)],summary:{count:6,average:5},histogram:[[5,6],[4,0],[3,0],[2,0],[1,0]],next_offset:url.searchParams.get('offset')==='0'?5:null},headers:{'Access-Control-Allow-Origin':'*'}});
   }
   return route.abort();
  });
  await page.goto('https://fixture.example');
  const original=fs.readFileSync('tests/test_existing_reviews_widget.cjs','utf8'),prefix="await page.evaluate(()=>{document.body.insertAdjacentHTML('beforeend',`";
  const html=original.split(prefix)[1].split('`)});')[0].replace('data-country="AU"',`data-country="${country}"`);
  await page.setContent('<style>.sc-reviews__list{display:flex;overflow:auto;width:350px}.sc-reviews__card{min-width:150px}.sc-reviews__thumbnail img{width:100px;height:100px}</style>'+html);
  const started=Date.now();await page.addScriptTag({content:fs.readFileSync(process.env.REVIEW_DRAFT_WIDGET_SOURCE,'utf8')});
  await page.waitForFunction(()=>document.querySelector('[data-review-archive]').children.length===5);
  const productThumb=page.locator('[data-review-archive] img[alt^="Product reviewed:"]');assert.equal(await productThumb.count(),1);assert.equal(await productThumb.getAttribute('loading'),'lazy');assert.equal(await productThumb.getAttribute('width'),'68');assert.match(await productThumb.getAttribute('src'),/width=136/);
  const shopBadge=page.getByRole('img',{name:'Verified by Shop',exact:true});assert.equal(await shopBadge.count(),1);assert.equal(await shopBadge.getAttribute('src'),'https://cdn.shopify.com/static/shop/Verified%20by%20Shop_Gray_EN.svg');assert.equal(await shopBadge.getAttribute('loading'),'lazy');
  assert.ok(Date.now()-started<1500);assert.equal(requests.length,1);
  assert.equal(await page.locator('[data-review-archive] time').count(),country==='AU'?1:0);
  assert.equal(await page.locator('[data-review-archive] .sc-reviews__verified').count(),1);
  assert.match(await page.locator('.sc-reviews__thumbnail img').first().getAttribute('srcset'),/640w/);
  assert.doesNotMatch(await page.locator('.sc-reviews__thumbnail img').first().getAttribute('srcset'),/1280w/);
  const expected=country==='AU'?['Fixture 0','Fixture 1','Fixture 2','Fixture 3']:['Fixture 1','Fixture 3','Fixture 0','Fixture 2'];
  assert.deepEqual((await page.locator('.sc-reviews__card .sc-reviews__name').allTextContents()).slice(0,4),expected);
  await page.locator('[data-review-more]').click();await page.getByRole('button',{name:'Retry loading reviews'}).waitFor();
  assert.equal(await page.locator('[data-review-archive] > *').count(),5);
  failMore=false;await page.locator('[data-review-more]').click();await page.waitForFunction(()=>document.querySelector('[data-review-archive]').children.length===6);
  assert.equal(await page.locator('[data-review-more]').isVisible(),false);
  assert.equal(await page.locator('video').count(),0);await page.getByRole('button',{name:'View review video',exact:true}).click();await page.locator('video').waitFor();assert.match(await page.locator('video').getAttribute('src'),/size=original/);assert.deepEqual(errors,[]);
 }finally{await browser.close()}
});

for(const buyer of [false,true])test('collection-style '+(buyer?'buyer':'storefront')+' form keeps inputs after failure and uploads photo/video once to OS',{skip:!process.env.REVIEW_FORM_FIXTURE||!process.env.REVIEW_PLAYWRIGHT_MODULE},async()=>{
 const {chromium}=require(process.env.REVIEW_PLAYWRIGHT_MODULE),browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});let posts=0,body='';
  await page.route('**/*',async route=>{
   if(route.request().method()==='POST'){posts++;body=route.request().postDataBuffer().toString();return route.fulfill({status:posts===1?400:200,contentType:'text/html',body:'<h1>Thank you</h1>'})}
   return route.fulfill({contentType:'text/html',body:fs.readFileSync(process.env.REVIEW_FORM_FIXTURE,'utf8').replace('value="synthetic-token"',buyer?'value=""':'value="synthetic-token"')});
  });
  await page.goto('https://fixture.example/reviews/write?product=1');
  assert.equal(await page.getByRole('radio',{name:'5 stars',exact:true}).isChecked(),true);await page.getByRole('radio',{name:'4 stars',exact:true}).check();
  await page.getByLabel('Name',{exact:true}).fill('Synthetic collector');await page.getByLabel('Your review',{exact:true}).fill('This synthetic edition looks great on the wall.');
  await page.locator('input[type=file]').setInputFiles([{name:'fixture.png',mimeType:'image/png',buffer:Buffer.from('synthetic photo')},{name:'fixture.webm',mimeType:'video/webm',buffer:Buffer.from('synthetic video')}]);
  assert.equal(await page.getByRole('checkbox').count(),0);await page.getByRole('button',{name:'Submit review'}).click();await page.getByRole('status').filter({hasText:'not submitted'}).waitFor();
  assert.equal(await page.getByLabel('Your review',{exact:true}).inputValue(),'This synthetic edition looks great on the wall.');
  await page.getByRole('button',{name:'Submit review'}).click();await page.getByRole('heading',{name:'Thank you for your review'}).waitFor();
  assert.equal(posts,2);assert.equal(/name="form_token"/.test(body),!buyer);assert.match(body,/fixture.webm/);assert.match(body,/fixture.png/);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 }finally{await browser.close()}
});
