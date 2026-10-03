// Loopback fixture only. Checks actual opacity, physical iframe identity and requests.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:768}});
  let imageRequests=0;
  await page.route('**/*',r=>{
   const u=new URL(r.request().url());
   if(u.hostname==='127.0.0.1')return r.continue();
   if(u.href==='https://cdn.shopify.com/fixture.png'){imageRequests++;return r.fulfill({contentType:'image/png',body:fs.readFileSync('tests/fixtures/checkout_product_generated.png')})}
   return r.abort();
  });
  await page.goto('http://127.0.0.1:8533/?fixture_checkout=1&fixture_profile=1&fixture_rerun=1');
  await page.getByText('Previewing: Fixture Collector · latest abandoned checkout',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Synthetic global rerun'}).click();await page.waitForTimeout(3000);
  const hydrationLabel=await page.getByText(/^Fixture hydrations: /).innerText();
  const frame=await(await page.locator('iframe[src*="crm_automation_stable_preview"]').elementHandle()).contentFrame();
  await frame.evaluate(()=>{window.instanceMarker='original';document.getElementById('email').contentWindow.scrollTo(0,200)});
  const idleScroll=await frame.evaluate(()=>document.getElementById('email').contentWindow.scrollY);
  const counts=()=>frame.evaluate(()=>({updates:previewUpdates,loads:previewLoads,instance:instanceMarker}));
  const initial=await counts();const initialImages=imageRequests;
  assert.ok(initialImages>0);
  await page.evaluate(()=>{window.minPreviewOpacity=1;window.sampler=setInterval(()=>{const e=document.querySelector('.st-key-crm-composer-preview iframe');if(!e)return;let o=1;for(let p=e;p;p=p.parentElement)o*=Number(getComputedStyle(p).opacity);window.minPreviewOpacity=Math.min(window.minPreviewOpacity,o)},20)});
  await page.waitForTimeout(Number(process.env.PREVIEW_IDLE_MS||90000));
  assert.deepEqual(await counts(),initial);
  assert.equal(imageRequests,initialImages);
  assert.equal(await page.evaluate(()=>minPreviewOpacity),1);
  await page.getByRole('button',{name:'Synthetic global rerun'}).click();await page.waitForTimeout(3000);
  assert.equal(await page.evaluate(()=>minPreviewOpacity),1);
  assert.deepEqual(await counts(),initial);
  await page.getByText('Fixture Shopify requests: 1',{exact:true}).waitFor();
  await page.getByText(hydrationLabel,{exact:true}).waitFor();
  assert.equal(await frame.evaluate(()=>document.getElementById('email').contentWindow.scrollY),idleScroll);
  console.log((Number(process.env.PREVIEW_IDLE_MS||90000)/1000)+'s idle + slow global rerun: 0 Shopify requests, 0 remounts, 0 reloads, 0 hydrations; minimum opacity 1');
  await page.getByRole('button',{name:'Save draft',exact:true}).click();await page.waitForTimeout(600);
  await page.locator('.st-key-crm-preview-devices button:visible').nth(1).click();await page.waitForTimeout(600);
  assert.deepEqual(await counts(),initial);
  await page.getByRole('button',{name:'Synthetic new checkout'}).click();await page.waitForTimeout(600);
  await page.getByText('Previewing: Fixture Collector · latest abandoned checkout',{exact:true}).waitFor();
  assert.deepEqual(await counts(),initial);
  const refresh=page.locator('.st-key-crm-preview-devices button:visible').nth(2);
  await refresh.click();
  await page.getByText('Previewing: New Collector · latest abandoned checkout',{exact:true}).waitFor();
  await frame.waitForFunction(n=>window.previewUpdates===n+1,initial.updates);
  assert.equal((await counts()).updates,initial.updates+1);
  await page.getByRole('button',{name:'Synthetic global rerun'}).click();await page.waitForTimeout(3000);
  await page.getByText('Fixture Shopify requests: 2',{exact:true}).waitFor();
  await refresh.click();await page.waitForTimeout(1600);
  assert.equal((await counts()).updates,initial.updates+1);
  await page.getByRole('button',{name:'Synthetic lookup failure'}).click();await page.waitForTimeout(600);
  await page.getByText('Fixture Shopify requests: 3',{exact:true}).waitFor();
  await refresh.click();await page.waitForTimeout(1600);
  await page.getByText('Previewing: New Collector · cached latest abandoned checkout',{exact:true}).waitFor();
  assert.equal((await counts()).updates,initial.updates+1);
  await page.getByRole('button',{name:'Synthetic global rerun'}).click();await page.waitForTimeout(3000);
  await page.getByText('Fixture Shopify requests: 4',{exact:true}).waitFor();
  assert.equal(await page.getByTestId('stException').count(),0);
  assert.equal(await page.evaluate(()=>minPreviewOpacity),1);
  console.log('Save/device reuse pin; new checkout remains pinned until manual refresh; each refresh one request; identical/failed refresh no HTML replacement');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
