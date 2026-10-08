// Actual production marker fragment; synthetic loopback data only.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const results={simulatedMarkerMs:1280,before:[],after:[]};
 for(const mode of ['before','after'])for(let i=0;i<3;i++){
  const context=await browser.newContext({viewport:{width:1440,height:900}});
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:8556/?mode=${mode}`);await page.locator('#ready').waitFor();
  await page.getByText('Other',{exact:true}).click();await page.getByText('Other page ready',{exact:true}).waitFor();
  let t=Date.now();await page.getByText('Orders',{exact:true}).click();await page.locator('#ready').waitFor();
  results[mode].push(Date.now()-t);
  await page.getByText('Other',{exact:true}).click();await page.getByText('Other page ready',{exact:true}).waitFor();
  // Delayed completion must not navigate back or introduce an exception.
  await page.waitForTimeout(1500);
  assert.equal(await page.locator('#ready').count(),0);assert.equal(await page.getByTestId('stException').count(),0);
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.deepEqual(errors,[]);await context.close();
 }
 fs.mkdirSync('.tmp-phase3-results',{recursive:true});fs.writeFileSync('.tmp-phase3-results/orders-browser.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
