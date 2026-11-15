// Synthetic loopback grid only. No production app or Companion connection.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:900}});let requests=[];
 await page.route('**/api/auto-editions/status/reset',async route=>{
  requests.push(route.request().postDataJSON());
  await page.request.post('http://127.0.0.1:8645/fixture-stage',{data:{stage:'Cancelling'+String.fromCharCode(8230)}});
  await route.fulfill({status:202,json:{ok:false,stage:'Cancelling'}});
 });
 await page.request.post('http://127.0.0.1:8645/fixture-stage',{data:{stage:'Preparing'}});
 await page.goto('http://127.0.0.1:8645');
 const button=page.locator('.sc-auto-reset:not(:disabled)').first();await button.waitFor();
 const pid=await button.getAttribute('data-product-gid');
 await button.click();const popup=page.getByRole('dialog',{name:'Reset design?',exact:true});
 assert.match(await popup.locator('p').innerText(),/clear its PSD mapping/);
 assert.equal(await popup.getByRole('button').count(),2);
 await popup.getByRole('button',{name:'Reset',exact:true}).dblclick().catch(()=>{});
 await page.waitForFunction(()=>SportsCaveEditionStatusState.rows.some(r=>r.cancelling));
 assert.equal(requests.length,1);assert.equal(requests[0].product_gid,pid);
 assert.equal(await page.locator('.sc-auto-reset:not(:disabled)').count(),0);
 assert.equal(await page.evaluate(pid=>sessionStorage.getItem('sc-design-reset:'+pid),pid),requests[0].request_id);
 await page.screenshot({path:'output/reset/cancelling.png'});
 // Automatic status refresh ends the pending state and releases the retained ID.
 await page.request.post('http://127.0.0.1:8645/fixture-stage',{data:{stage:'Queued'}});
 await page.evaluate(()=>SportsCaveEditionStatus.refresh());
 await page.waitForFunction(pid=>!sessionStorage.getItem('sc-design-reset:'+pid),pid);
 assert.equal(requests.length,1);assert.equal(await page.getByRole('dialog').count(),0);
 await page.close();console.log('Pending cancellation, duplicate click, confirmation and automatic status resume passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
