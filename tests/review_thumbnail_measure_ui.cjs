// Actual local endpoints and artwork JPEGs. No scrolling in load measurements.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const f=JSON.parse(process.env.SC_REVIEW_MEASURE),browser=await chromium.launch({channel:'msedge',headless:true});try{
 const context=await browser.newContext({viewport:{width:1280,height:800}});await context.addCookies([{name:f.cookieName,value:f.cookie,url:f.url}]);
 const page=await context.newPage(),report=[],errors=[],statuses=[];page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.url().includes('/bulk/'))statuses.push([r.url(),r.status()]);});
 for(const phase of ['cold','warm']){
  let bytes=0;const reads=[],serverTimings=[];
  const receive=response=>{if(response.headers()['server-timing'])serverTimings.push({path:new URL(response.url()).pathname,timing:response.headers()['server-timing']});if(response.url().includes('/bulk/'))reads.push(response.body().then(b=>{bytes+=b.length;}).catch(()=>{}));};page.on('response',receive);
  const start=performance.now();await page.goto(f.url);await page.evaluate(ids=>postMessage({type:'sports-cave-bulk-products',product_gids:ids},location.origin),f.ids);
  await page.locator('#grid input:not(:disabled)').first().waitFor({timeout:15000}).catch(async e=>{console.log(JSON.stringify({body:await page.locator('body').innerText(),errors,statuses,timings:await page.evaluate(()=>window.reviewTimings)}));throw e;});const first=performance.now()-start;
  await page.waitForFunction(()=>[...document.querySelectorAll('#grid figure')].filter(n=>{const r=n.getBoundingClientRect();return r.bottom>0&&r.top<innerHeight;}).every(n=>!n.querySelector('input').disabled),null,{timeout:15000}).catch(async e=>{console.log(JSON.stringify({body:await page.locator('body').innerText(),errors,statuses,timings:await page.evaluate(()=>window.reviewTimings)}));throw e;});
  const resolved=performance.now()-start;await Promise.all(reads);page.off('response',receive);
  const images=await page.locator('#grid img').evaluateAll(items=>items.map(im=>({width:im.naturalWidth,loaded:im.complete})));
  assert(images.every(im=>im.loaded&&im.width>0&&im.width<=300));
  report.push({phase,first_visible_ms:+first.toFixed(2),first_viewport_resolved_ms:+resolved.toFixed(2),browser_api_bytes:bytes,serverTimings,thumbnail_delivery:await page.evaluate(()=>performance.getEntriesByType('resource').filter(r=>r.name.includes('/bulk/previews')).map(r=>({duration_ms:r.duration,wire_bytes:r.transferSize,payload_bytes:r.encodedBodySize}))),timings:await page.evaluate(()=>reviewTimings)});
  await page.screenshot({path:f.screenshot+'-'+phase+'.png'});
 }
 fs.writeFileSync(f.result,JSON.stringify(report,null,2));console.log(JSON.stringify(report));await context.close();
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
