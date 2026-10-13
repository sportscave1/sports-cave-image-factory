// Actual Streamlit toolbar/canvas with synthetic inputs; no external requests.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1100,height:950}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));const results={flows:{},layouts:[]};
 await page.route('**/*',r=>{const url=new URL(r.request().url());if(url.hostname==='127.0.0.1')return r.continue();if(url.hostname==='cdn.shopify.com')return r.fulfill({contentType:'image/png',body:fs.readFileSync('tests/fixtures/checkout_product_generated.png')});return r.abort()});
 const bar=()=>page.locator('[class*="st-key-crm-preview-toolbar-"]');
 const frame=()=>page.frameLocator('.st-key-crm-composer-preview iframe');
 const selectFlow=async kind=>{await page.getByRole('combobox').first().click();await page.getByRole('option',{name:kind,exact:true}).click();};
 const ready=async text=>{await frame().getByText(text,{exact:true}).first().waitFor({timeout:20000});assert.equal(await page.getByTestId('stException').count(),0);};
 try{
  const cold=performance.now();await page.goto('http://127.0.0.1:18731/');await ready('Fixture Ada Motorsport artwork');results.cold_browser_ms=performance.now()-cold;
  assert.equal(await page.getByText('Example customer',{exact:true}).count(),0);
  assert.equal(await page.locator('.sc-email-size').count(),0);
  for(const width of [1100,600,390,320]){
   await page.setViewportSize({width,height:950});await page.waitForTimeout(100);
   const box=await bar().boundingBox();assert.ok(box.height>=36&&box.height<=42,JSON.stringify(box));
   const overflow=await bar().evaluate(e=>e.scrollWidth>e.clientWidth+2);assert.equal(overflow,false,'toolbar overflow '+width);
   const boxes=await bar().locator('button').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}}).filter(r=>r.w>0));
   for(let i=1;i<boxes.length;i++)assert.ok(boxes[i].x>=boxes[i-1].x+boxes[i-1].w-1,'overlap at '+width);
   results.layouts.push({width,height:box.height});await page.screenshot({path:'.tmp-preview-performance/toolbar-'+width+'.png'});
  }
  await page.setViewportSize({width:1100,height:950});
  await bar().getByRole('button',{name:/Previewing:/}).click();
  const choice=page.getByTestId('stPopoverBody').getByRole('combobox');await choice.waitFor();await choice.click();await page.getByRole('option',{name:/Fixture Grace/}).click();
  await page.keyboard.press('Escape');
  const switched=performance.now();await ready('Fixture Grace Motorsport artwork');results.customer_switch_browser_ms=performance.now()-switched;
  assert.ok((await bar().innerText()).includes('Fixture Grace'));
  await page.setViewportSize({width:320,height:950});await page.waitForTimeout(100);
  assert.equal(await bar().evaluate(e=>e.scrollWidth>e.clientWidth+2),false,'long-name overflow');
  await page.screenshot({path:'.tmp-preview-performance/toolbar-long-name-320.png'});
  await page.setViewportSize({width:1100,height:950});
  const prior=await frame().locator('img').first().getAttribute('src');assert.ok(prior.includes('fixture-1'));
  const t=performance.now();await bar().locator('[class*="checkout_refresh"] button:visible').click();
  await ready('Fixture Grace Motorsport artwork');assert.equal(await frame().locator('img').first().getAttribute('src'),prior);results.refresh_visible_ms=performance.now()-t;
  await page.waitForTimeout(500);
  const html=page.getByRole('textbox',{name:'Fixture HTML'});const source=await html.inputValue();
  const edited=performance.now();await html.fill(source.replace('Your artwork, chosen by you','Edited fixture heading'));await html.press('Tab');await frame().getByText('Edited fixture heading',{exact:true}).waitFor();results.html_edit_browser_ms=performance.now()-edited;
  await page.getByRole('button',{name:'Close/open editor'}).click();const warm=performance.now();await page.getByRole('button',{name:'Close/open editor'}).click();await frame().getByText('Edited fixture heading',{exact:true}).waitFor();results.warm_reopen_browser_ms=performance.now()-warm;
  await bar().locator('[class*="device_Mobile"] button:visible').click();await ready('Fixture Grace Motorsport artwork');
  await bar().locator('[class*="device_Desktop"] button:visible').click();await ready('Fixture Grace Motorsport artwork');
  await page.getByRole('button',{name:'Collection template'}).click();
  await ready('Fixture 3');assert.equal(await frame().locator('img').count(),6,'six matching collection artworks');
  for(const kind of ['welcome','win_back','fulfilled','abandoned']){
   const start=performance.now();await selectFlow(kind);
   if(kind==='welcome')await ready('Fixture Welcome subscriber content');
   else if(kind==='abandoned')await frame().locator('img').first().waitFor({timeout:20000});
   else await ready('Fixture Ada Motorsport artwork');
   results.flows[kind]={open_ms:performance.now()-start};assert.equal(await bar().count(),1);assert.equal(await page.getByTestId('stException').count(),0);
  }
  assert.deepEqual(errors,[]);fs.writeFileSync('.tmp-preview-performance/browser-results.json',JSON.stringify(results,null,2));console.log('PASS actual Streamlit: five flows, compact 36–42px toolbar, customer switching, retained refresh, editing, reopen and devices');console.log(JSON.stringify(results));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
