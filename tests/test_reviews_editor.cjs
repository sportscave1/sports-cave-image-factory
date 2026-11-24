const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const enabled=Boolean(process.env.REVIEW_PLAYWRIGHT_MODULE&&process.env.REVIEW_FORM_FIXTURE&&process.env.REVIEW_FORM_HEADERS);
test('review form loads through both Shopify editor ancestors and rejects unrelated parents',{skip:!enabled,timeout:15000},async()=>{
 const {chromium}=require(process.env.REVIEW_PLAYWRIGHT_MODULE),browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage(),errors=[];page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
  const headers=JSON.parse(fs.readFileSync(process.env.REVIEW_FORM_HEADERS,'utf8'));
  await page.route('**/*',route=>{
   const host=new URL(route.request().url()).hostname;
   if(host==='sports-cave-image-factory.onrender.com')return route.fulfill({contentType:'text/html',headers,body:fs.readFileSync(process.env.REVIEW_FORM_FIXTURE,'utf8')});
   const target=host==='admin.shopify.com'||host==='unrelated.example'?'https://online-store-web.shopifyapps.com/editor':host==='online-store-web.shopifyapps.com'?'https://www.sportscaveshop.com/pages/reviews':'https://sports-cave-image-factory.onrender.com/reviews/write';
   return route.fulfill({contentType:'text/html',body:'<!doctype html><iframe title="Nested preview" style="width:100%;height:700px" src="'+target+'"></iframe>'});
  });
  await page.goto('https://admin.shopify.com/editor');
  const form=page.frameLocator('iframe').frameLocator('iframe').frameLocator('iframe');
  await form.getByRole('heading',{name:'How does it look in your space?'}).waitFor();
  assert.equal(await form.getByRole('radio').count(),5);
  assert.equal(errors.length,0);
  const blocked=page.waitForEvent('console',{predicate:m=>m.text().includes('frame-ancestors'),timeout:5000});
  await page.goto('https://unrelated.example/editor');
  await blocked;
  assert.ok(errors.some(message=>message.includes('frame-ancestors')));
 }finally{await browser.close()}
});
