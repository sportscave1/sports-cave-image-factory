const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const source=process.env.REVIEW_EXISTING_WIDGET_SOURCE;
test('existing theme reads native reviews, includes video and preserves bounded playback', {skip:!source}, async()=>{
  const {chromium}=require(process.env.REVIEW_PLAYWRIGHT_MODULE);
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try {
    const page=await browser.newPage({viewport:{width:320,height:740}}),requests=[],errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    const origin='https://sports-cave-image-factory.onrender.com';
    const media=id=>origin+'/reviews/media/'+id+'?size=';
    const rows=[{id:'fixture-photo',reviewer_name:'Photo fixture',rating:5,title:'Photo fixture',body:'Synthetic image review',verified_purchase:false,media:[{kind:'image',url:media('aaaa')+'1280',thumbnail_url:media('aaaa')+'320',poster_url:media('aaaa')+'1280'}]},
      {id:'fixture-video',reviewer_name:'Video fixture',rating:4,title:'Video fixture',body:'Synthetic video review',verified_purchase:false,media:[{kind:'video',url:media('bbbb')+'original',thumbnail_url:media('bbbb')+'320',poster_url:media('bbbb')+'1280'}]},
      {id:'fixture-text',reviewer_name:'Text fixture',rating:5,title:'Text fixture',body:'Synthetic text review',verified_purchase:false,media:[]}];
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());requests.push(url.href);
      if(url.pathname==='/reviews/public')return route.fulfill({json:{reviews:url.searchParams.get('offset')==='2'?rows.slice(2):rows.slice(0,2),next_offset:url.searchParams.get('offset')==='2'?null:2,summary:{count:3,average:4.67}},headers:{'Access-Control-Allow-Origin':'*'}});
      return route.abort();
    });
    await page.setContent('<style>.sc-reviews__list{display:flex;overflow:auto;width:280px}.sc-reviews__card{min-width:120px}.sc-reviews__thumbnail img{width:90px;height:90px}dialog{box-sizing:border-box;width:94vw;max-width:860px}video{max-width:100%}</style>');
    await page.addScriptTag({content:fs.readFileSync(source,'utf8')});
    await page.evaluate(()=>{document.body.insertAdjacentHTML('beforeend',`<sc-customer-reviews data-layout="carousel" data-shop="sportscave-nb.myshopify.com" data-locale="en-AU" data-country="AU"><div class="sc-reviews__inner"><p data-review-summary hidden></p><ul data-review-histogram hidden></ul><div class="sc-reviews__list" data-review-list></div><button data-review-step="-1"></button><button data-review-step="1"></button><section><div data-review-archive></div><p data-review-empty hidden>No matching reviews.</p><button data-review-more hidden>Load more</button><p data-review-status></p></section><dialog data-review-dialog><button class="sc-reviews__close">Close</button><div><div hidden><div data-review-media></div><div data-review-media-controls hidden><span data-review-media-count></span></div></div><div data-review-detail></div></div></dialog></div></sc-customer-reviews>`)});
    await page.waitForFunction(()=>document.querySelector('[data-review-archive]')?.children.length===3);
    assert.equal(await page.locator('.sc-reviews__verified').count(),0);
    assert.equal(await page.locator('.sc-reviews__row-photo').count(),2);
    assert.equal(await page.locator('video').count(),0);
    await page.locator('[data-review-index="1"]').first().click();
    const video=page.locator('video');await video.waitFor();
    assert.equal(await video.getAttribute('preload'),'none');
    assert.equal(await video.getAttribute('autoplay'),null);
    assert.match(await video.getAttribute('poster'),/size=1280/);
    const box=await video.boundingBox();assert.ok(box.width<=320&&box.height<=740*.65+1);
    await page.locator('.sc-reviews__close').click();
    await video.waitFor({state:'detached'});
    assert.equal(requests.filter(url=>url.includes('judge.me')||url.includes('judgeme')).length,0);
    assert.equal(requests.filter(url=>url.includes('/reviews/public')&&!url.includes('summary=1')).length,2);
    assert.deepEqual(errors,[]);
  } finally {await browser.close()}
});
