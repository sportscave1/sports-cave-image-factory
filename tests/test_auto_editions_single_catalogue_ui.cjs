const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{for(const width of [1280,390]){
 const page=await browser.newPage({viewport:{width,height:700}});let reads=0;
 await page.clock.install();await page.route('**/*',route=>{
  const url=new URL(route.request().url());
  if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/auto_editions/onboarding.html','utf8')});
  if(url.pathname.endsWith('/onboarding')){reads++;return route.fulfill({json:{continuous_enabled:true,catalogue_total:334,mapped:285,rows:[{product_gid:'p',product_title:'One artwork',status:'Cloud Ready',preparation_hash:'a'.repeat(64)}],counts:{'Cloud Ready':16,'Preparing':1,'Queued':110,'Needs Review':45,'Needs PSD Repair':41,'Failed':72,'Uploaded':61,'Remaining':269},host:{last_seen:'fixture heartbeat'},processing:'Companion Connected'}});}
  return route.fulfill({status:404});
 });
 await page.goto('https://catalogue.local.test/?summary=1');await page.getByText('Catalogue: 334 (285 PSD mapped)',{exact:false}).waitFor();
 assert.equal(await page.locator('select:visible').count(),0);assert.equal(await page.locator('#products option').count(),0);
 assert.equal(await page.getByRole('button',{name:'Review prepared artwork'}).isVisible(),false);
 assert.equal(await page.getByRole('button',{name:'Prepare Now'}).isVisible(),false);
 assert(!(await page.locator('#summary').innerText()).includes('Remaining'));
 assert((await page.locator('#summary').getAttribute('title')).includes('subsets, not additional products'));
 await page.clock.runFor(25100);await page.waitForFunction(()=>!loading);assert.equal(reads,2);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 fs.mkdirSync('output/single-catalogue',{recursive:true});await page.screenshot({path:`output/single-catalogue/summary-${width}.png`});
 await page.close();console.log(`One catalogue, subset counts, no second product picker and lightweight polling passed ${width}`);
 }}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
