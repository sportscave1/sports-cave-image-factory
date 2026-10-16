// No intercepted images: signed local cookie -> actual endpoints -> verified PNGs -> real JPEGs.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const f=JSON.parse(process.env.SC_PREVIEW_FIXTURE),browser=await chromium.launch({channel:'msedge',headless:true});try{
 const context=await browser.newContext({viewport:{width:1200,height:800}});await context.addCookies([{name:f.cookieName,value:f.cookie,url:f.url}]);
 const page=await context.newPage(),errors=[],responses=[];page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.url().includes('/bulk/'))responses.push({url:r.url(),status:r.status(),type:r.headers()['content-type']});});
 const open=async()=>{await page.goto(f.url);await page.evaluate(ids=>postMessage({type:'sports-cave-bulk-products',product_gids:ids},location.origin),f.ids);await page.locator('#grid figure').first().waitFor();await page.locator('#grid input:not(:disabled)').first().waitFor();};
 const start=Date.now();await open();const first=Date.now()-start;
 assert.equal(await page.locator('#all').count(),0);assert.equal(await page.getByRole('button',{name:'Approve Selected',exact:true}).count(),1);
 assert((await page.locator('#grid input:not(:disabled)').count())<40,'Lazy initial batch');
 async function walk(){for(let i=0;i<40;i++){
  if(i&&i%10===0){await page.locator('#next').click();await page.waitForFunction(n=>document.querySelector('#grid input')?.value.endsWith('/'+n),i+1);}
  const card=page.locator('#grid figure').nth(i%10);await card.scrollIntoViewIfNeeded();await card.locator('input:not(:disabled)').waitFor({timeout:20000});assert(await card.locator('img').evaluate(im=>im.complete&&im.naturalWidth>0&&im.naturalWidth<=300));
 }}
 await walk();
 const total=Date.now()-start,timings=await page.evaluate(()=>reviewTimings);await page.locator('#grid input').first().check();await page.locator('#approve').click();assert(await page.locator('#accept').isDisabled());await page.locator('#cancel').click();
 await page.locator('#grid img').last().click();await page.waitForFunction(()=>document.querySelector('#large-image').naturalWidth===1200);await page.locator('#close-large').click();
 const before=responses.length,reopenStart=Date.now();await open();const reopen=Date.now()-reopenStart;
 await walk();

 const warm=responses.slice(before);assert(!warm.some(r=>r.url.includes('/image')),'Reopen uses binary cached batches only');assert(warm.some(r=>r.type?.startsWith('multipart/form-data')));assert.deepEqual(errors,[]);
 // Revoke the account cookie: actual image endpoint must fail closed, never return JPEG.
 await context.clearCookies();const imageURL=responses.find(r=>r.url.includes('/image')&&r.status===200).url;
 const denied=await context.request.get(imageURL);assert.equal(denied.status(),403);
 const report={source:'Real local HTTP, signed cookie, actual image/cache endpoints, streamed synthetic 4000x2000 PNGs, isolated PostgreSQL; no live Dropbox',designs:40,first_visible_ms:first,navigation_inclusive_elapsed_ms:total,reopen_first_visible_ms:reopen,timings,image_responses:responses.filter(r=>r.url.includes('/image')).length,warm_individual_requests:0};
 fs.mkdirSync('output/bulk-preview-fix',{recursive:true});fs.writeFileSync('output/bulk-preview-fix/real-browser.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));await context.close();
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
