// Product->collection gallery transition on the same verified order.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true}),result={};
 try{for(const [label,port]of [['before',18732],['after',18731]]){
  const page=await browser.newPage({viewport:{width:1100,height:950}});
  await page.route('**/*',r=>{const u=new URL(r.request().url());if(u.hostname==='127.0.0.1')return r.continue();if(u.hostname==='cdn.shopify.com')return r.fulfill({contentType:'image/png',body:fs.readFileSync('tests/fixtures/checkout_product_generated.png')});return r.abort()});
  await page.goto('http://127.0.0.1:'+port+'/?flow=post_purchase');
  const frame=()=>page.frameLocator('.st-key-crm-composer-preview iframe');
  await frame().getByText('Fixture Ada Motorsport artwork',{exact:true}).first().waitFor();await page.waitForTimeout(500);
  const counters=async()=>{const ack=await page.locator('#fixture-counter-version').innerText();await page.getByRole('button',{name:'Fixture counters',exact:true}).click();await page.waitForFunction(v=>document.querySelector('#fixture-counter-version')?.textContent!==v,ack);return JSON.parse(await page.locator('#fixture-metrics').innerText())};
  const first=await counters(),start=performance.now();await page.getByRole('button',{name:'Collection template',exact:true}).click();
  await frame().getByText('Fixture 3',{exact:true}).first().waitFor();const elapsed=performance.now()-start;await page.waitForTimeout(500);const last=await counters();
  assert.equal(await frame().locator('img').count(),6);result[label]={transition_ms:elapsed,added_query_calls:last.query_actual-first.query_actual,added_product_calls:last.products_actual-first.products_actual,added_customer_calls:last.customer_actual-first.customer_actual};await page.close();
 }}finally{await browser.close()}
 assert.equal(result.after.added_customer_calls,0);assert.equal(result.after.added_product_calls,0);
 fs.writeFileSync('.tmp-preview-ultimate/gallery-reuse.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exit(1)});
