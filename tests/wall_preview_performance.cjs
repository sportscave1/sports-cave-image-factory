const {chromium}=require('playwright'),fs=require('fs');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});let results=[];try{
for(const theme of ['188890644787','189335863603'])for(let run=0;run<3;run++){
 const page=await browser.newPage({viewport:{width:1366,height:768}});let requests=0;page.on('request',()=>requests++);
 await page.addInitScript(()=>{window.metrics={lcp:0,cls:0};new PerformanceObserver(l=>l.getEntries().forEach(e=>metrics.lcp=e.startTime)).observe({type:'largest-contentful-paint',buffered:true});new PerformanceObserver(l=>l.getEntries().forEach(e=>{if(!e.hadRecentInput)metrics.cls+=e.value;})).observe({type:'layout-shift',buffered:true});});
 await page.goto('https://www.sportscaveshop.com/products/legends-never-die-kobe-bryant-michael-jordan-wall-art?preview_theme_id='+theme,{waitUntil:'load'});
 // Fixed observation window for comparable lab measurements; not a retry mechanism.
 await page.waitForTimeout(2000);
 const m=await page.evaluate(()=>({...metrics,theme:Shopify.theme.id,initialized:document.querySelector('[data-sc-wall-root]')?.getAttribute('data-sc-wall-initialized'),featureRequests:performance.getEntriesByType('resource').filter(r=>r.name.includes('sports-cave-wall-preview')||r.name.includes('sports-cave-image-protection')||r.name.includes('storefront-protection/config')).map(r=>({url:r.name,transfer:r.transferSize,duration:r.duration})),domContentLoaded:performance.getEntriesByType('navigation')[0].domContentLoadedEventEnd}));results.push({run,requests,...m});console.log(JSON.stringify(results.at(-1)));await page.close();
}fs.writeFileSync('output/wall-preview-performance.json',JSON.stringify(results,null,2));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
