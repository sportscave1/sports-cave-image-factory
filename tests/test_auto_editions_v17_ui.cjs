const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{for(const width of [1280,390]){
 const page=await browser.newPage({viewport:{width,height:800}});let reads=0,unavailable=false;
 const rows=[{product_gid:'p',product_title:'Synthetic uploaded artwork',status:'Blocked',display_status:'Needs Review',reason:'Visual review required',preparation_hash:'a'.repeat(64)},
 {product_gid:'q',product_title:'Synthetic catalogue artwork',status:'Awaiting preparation',display_status:'Queued',reason:'Continuous mapped catalogue'}];
 const counts={'Total mapped':285,'Cloud Ready':16,'Preparing':1,'Queued':166,'Needs Review':1,'Needs PSD Repair':26,'Failed':75,'Remaining':269,'Uploaded':17,'Production Ready':0};
 await page.route('**/*',route=>{const u=new URL(route.request().url());
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/auto_editions/onboarding.html','utf8')});
  if(u.pathname.endsWith('/onboarding')){reads++;return unavailable?route.fulfill({status:503,json:{error:'Authoritative status unavailable'}}):route.fulfill({json:{continuous_enabled:true,rows,mapped:285,counts,host:{last_seen:'synthetic heartbeat'},processing:'Companion Connected',current:{title:'Active artwork',stage:'Uploading'},last_success:{title:'Completed artwork',at:'synthetic checkpoint'}}});}
  return route.fulfill({status:404});
 });
 await page.clock.install();await page.goto('https://v17.local.test/');await page.getByText('Total mapped: 285',{exact:false}).waitFor();
 assert.equal(await page.locator('#resume').isVisible(),false);
 assert.equal((await page.locator('#summary').innerText()).split(' · ').length,8);
 assert((await page.locator('#host').innerText()).includes('Active artwork — Uploading'));
 assert((await page.locator('#host').innerText()).includes('Completed artwork'));
 assert.equal(reads,1);await page.clock.runFor(24900);assert.equal(reads,1);
 await page.clock.runFor(200);await page.waitForFunction(()=>!loading);assert.equal(reads,2);
 await page.locator('#products').selectOption('p');await page.getByRole('button',{name:'Review prepared artwork'}).click();await page.locator('#confirm').check();
 await page.clock.runFor(50000);assert.equal(reads,2);
 await page.getByRole('button',{name:'Refresh',exact:true}).click();await page.waitForFunction(()=>!loading);
 assert.equal(reads,3);assert.equal(await page.locator('#confirm').isChecked(),true);assert.equal(await page.locator('#quality').isVisible(),true);
 await page.locator('#products').selectOption('q');await page.locator('#refresh').focus();
 await page.evaluate(()=>window.scrollTo(0,20));const scroll=await page.evaluate(()=>scrollY);
 await page.clock.runFor(25000);await page.waitForFunction(()=>!loading);assert.equal(reads,4);
 assert.equal(await page.locator('#products').inputValue(),'q');assert.equal(await page.evaluate(()=>scrollY),scroll);
 unavailable=true;await page.getByRole('button',{name:'Refresh',exact:true}).click();await page.getByText('Authoritative status unavailable',{exact:true}).waitFor();
 assert((await page.locator('#summary').innerText()).includes('Total mapped: 285'));
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 fs.mkdirSync('output/v17',{recursive:true});await page.screenshot({path:`output/v17/onboarding-${width}.png`});
 await page.close();console.log(`V17 counters, polling, review/selection/scroll preservation and unavailable state passed ${width}`);
 }}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
