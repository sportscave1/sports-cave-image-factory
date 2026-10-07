const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('fs');
const theme=process.env.SC_THEME_ID||'189335863603',origin='https://www.sportscaveshop.com';
(async()=>{const browser=await chromium.launch({channel:process.env.SC_BROWSER||'chrome',headless:true});try{
const page=await browser.newPage({viewport:{width:1366,height:768},acceptDownloads:true});let errors=[],assets=[];
page.on('pageerror',e=>errors.push(e.stack));page.on('response',r=>{if(r.url().includes('/assets/sports-cave-'))assets.push({url:r.url(),status:r.status()});});
await page.route('**/api/wall-previews**',r=>r.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'},body:'{"ok":true,"archive_status":"queued"}'}));
await page.addInitScript(()=>{window.scPerf={cls:0,lcp:0};new PerformanceObserver(l=>l.getEntries().forEach(e=>{if(!e.hadRecentInput)scPerf.cls+=e.value;})).observe({type:'layout-shift',buffered:true});new PerformanceObserver(l=>l.getEntries().forEach(e=>scPerf.lcp=e.startTime)).observe({type:'largest-contentful-paint',buffered:true});});
for(const path of ['/','/collections/all','/products/legends-never-die-kobe-bryant-michael-jordan-wall-art']){
 await page.goto(origin+path+(theme==='188890644787'?'':'?preview_theme_id='+theme),{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>window.__scProtectionReady);assert.equal(String(await page.evaluate(()=>Shopify.theme.id)),theme);
 const art=page.locator(path==='/'?'.schero__img':path.startsWith('/collections')?'.sc-product-media img':'.product-media img').first();await art.waitFor({state:'attached'});
 assert.equal(await art.evaluate(e=>e.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true}))),false);
 assert.equal(await art.evaluate(e=>e.dispatchEvent(new Event('dragstart',{bubbles:true,cancelable:true}))),false);
 await page.emulateMedia({media:'print'});assert.equal(await art.evaluate(e=>getComputedStyle(e).visibility),'hidden');await page.emulateMedia({media:'screen'});
 assert.equal(await page.locator('.sc-artwork-watermark').count(),0);
 assert(await page.locator('link[rel="canonical"]').getAttribute('href'));
 console.log('PASS protection, print, watermark OFF, canonical',path,await page.evaluate(()=>scPerf));
 console.log('Page-load errors before opening wall preview',JSON.stringify(errors));
}
const baselineErrors=new Set(errors.map(e=>e.split('\n')[0]));
const cookies=page.getByRole('button',{name:/reject all|decline/i});if(await cookies.count())await cookies.first().click();
const bar=page.frameLocator('#PBarNextFrame').getByRole('button',{name:/hide/i});try{await bar.first().waitFor({state:'visible',timeout:8000});await bar.first().click();}catch(e){}
await page.locator('[data-sc-wall-open]').click();await page.locator('[data-sc-wall-upload-input]').setInputFiles('output/image-protection-test-room.jpg');await page.locator('[data-sc-wall-quick-preview]').click();await page.locator('[data-sc-wall-art]').waitFor({state:'visible'});
const box=await page.locator('[data-sc-wall-art]').boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+20,box.y+box.height/2+10);await page.mouse.up();await page.locator('[data-sc-wall-confirm]').click();
await page.waitForFunction(()=>document.querySelector('[data-sc-wall-confirm-label]').textContent.includes('Your wall preview is ready'));await page.locator('[data-sc-wall-save]').click();await page.locator('[data-sc-wall-download-email]').waitFor({state:'visible'});await page.keyboard.press('Escape');
await page.locator('[data-sc-wall-sticky-secure]').click();await page.waitForFunction(()=>document.querySelector('cart-drawer')?.getAttribute('aria-hidden')==='false');
const cart=await page.request.get(origin+'/cart.js');const data=await cart.json();assert.equal(data.item_count,1);assert.equal(data.items[0].handle,'legends-never-die-kobe-bryant-michael-jordan-wall-art');console.log('PASS real Add to Cart and cart drawer',data.items[0].variant_title);
const checkout=page.locator('cart-drawer [name="checkout"],cart-drawer a[href="/checkout"]');assert(await checkout.count(),'checkout handoff exists');
// Remove only this isolated test session's one line; never touch a customer order.
const removed=await page.request.post(origin+'/cart/change.js',{data:{id:data.items[0].key,quantity:0}});assert.equal((await removed.json()).item_count,0);
await page.screenshot({path:'output/deployed-shopping-'+theme+'.png'});
assert(assets.every(a=>a.status===200));assert.equal(errors.filter(e=>!baselineErrors.has(e.split('\n')[0])&&!e.includes('boostymark-regionblock')).length,0,errors.join('\n'));
console.log('PASS scoped cart cleanup, asset HTTP 200, no new runtime errors');
fs.writeFileSync('output/deployed-shopping-'+theme+'.json',JSON.stringify({theme,errors,assets},null,2));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
