// Run only against the fabricated loopback fixture; deny external HTTP.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1500,height:1000}});
  await context.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
  const page=await context.newPage();
  await page.goto(process.argv[2]||'http://127.0.0.1:8527');
  const row=page.locator('.sc-home-row');
  await row.waitFor({timeout:30000});
  assert.equal(await row.count(),1);
  assert.equal((await row.locator('.sc-col-delivered').innerText()).trim().split('\n')[0],'0');
  const href=await row.locator('a').getAttribute('href');
  assert.match(await row.locator('.sc-col-status').innerText(),/Sent/);
  const started=performance.now();
  await page.getByRole('button',{name:'Receive simulated delivered callback',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.sc-home-row .sc-col-delivered')?.innerText.trim().split('\n')[0]==='1',{},{timeout:30000});
  const elapsed=performance.now()-started;
  assert.equal(await row.locator('a').getAttribute('href'),href);
  assert.match(await row.locator('.sc-col-status').innerText(),/Sent/);
  await page.reload();
  await page.waitForFunction(()=>document.querySelector('.sc-home-row .sc-col-delivered')?.innerText.trim().split('\n')[0]==='1',{},{timeout:15000});
  assert.equal(await row.count(),1);
  console.log(JSON.stringify({scheduled_callback_to_confirmed_counter_ms:Math.round(elapsed),included_arrival_delay_ms:3000,counter_after_refresh:1,same_sent_campaign:true,external_requests_allowed:false}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
