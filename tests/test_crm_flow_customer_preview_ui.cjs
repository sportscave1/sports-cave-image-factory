// Real reactive preview code, fabricated products, all network requests denied.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage();const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>r.request().url()==='https://cdn.shopify.com/fixture-artwork.jpg'
  ?r.fulfill({contentType:'image/png',body:fs.readFileSync('tests/fixtures/checkout_product_generated.png')}):r.abort());
 const cases=JSON.parse(fs.readFileSync('.tmp-flow-preview/browser-input.json','utf8'));
 try{
  for(const test of cases)for(const width of [600,390,320]){
   await page.setViewportSize({width,height:900});await page.setContent('<!doctype html><html><body></body></html>');
   await page.addScriptTag({content:fs.readFileSync('components/crm_sections/preview.js','utf8')});
   await page.evaluate(({model,sections})=>{
    document.body.style.margin='0';const root=document.createElement('div');root.id='preview';document.body.append(root);
    root.innerHTML=sections.map(s=>SCPreview.sectionHtml(s,model,sections)).join('');
   },test);
   assert.equal(await page.locator('img').count(),test.key==='purchased'?1:6);
   await page.waitForFunction(()=>[...document.images].every(i=>i.complete&&i.naturalWidth>0));
   assert.equal(await page.locator('body').evaluate(e=>e.scrollWidth>innerWidth),false,'overflow '+test.key+' '+width);
   assert.ok((await page.locator('body').innerText()).includes('Fixture'));
   assert.equal(await page.locator('a[href]').count(),0,'preview links are inert');
   // A keystroke changes authored card layout immediately and keeps bindings.
   const edited=await page.evaluate(({model,sections})=>{
    const s={...sections[0],html:sections[0].html.replace('font-size:22px;font-family:Georgia','font-size:18px;font-family:Arial').replace('Explore artwork','Edited button')};
    const output=SCPreview.sectionHtml(s,model,[s]);document.querySelector('#preview').innerHTML=output;return output;
   },test);
   assert.ok(edited.includes('Edited button'));assert.ok(edited.includes('font-size:18px'));
   assert.ok(!edited.includes('[[product.')&&!edited.includes('SC_COLLECTOR'));
   assert.equal(await page.locator('img').count(),test.key==='purchased'?1:6);
   await page.screenshot({path:'.tmp-flow-preview/'+test.key+'-'+width+'.png',fullPage:true});
  }
  assert.deepEqual(errors,[]);
  console.log('PASS purchased/recommendation bindings, reactive HTML edits, inert links and layouts at 600/390/320px; network denied');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
