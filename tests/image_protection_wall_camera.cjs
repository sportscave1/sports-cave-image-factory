const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('fs');
const fixture=require('./wall_preview_completion_fixture.cjs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']});
 try{
 const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true,userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1',permissions:['camera']});let errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>{
  const u=r.request().url();
  if(u.endsWith('/storefront-protection.js'))return r.fulfill({contentType:'application/javascript',body:fs.readFileSync('storefront-protection.js','utf8')});
  if(u.endsWith('/api/storefront-protection/config'))return r.fulfill({contentType:'application/json',body:'{"enabled":true}'});
  if(u.endsWith('/products/test-art'))return r.fulfill({contentType:'text/html',body:fixture()+'<script src="/storefront-protection.js" defer></script>'});
  if(u.endsWith('/art.png'))return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"><rect width="500" height="500" fill="navy"/></svg>'});
  if(u.includes('/api/wall-previews'))return r.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:'{"ok":true,"archive_status":"queued"}'});
  return r.abort();
 });
 await page.goto('https://www.sportscaveshop.com/products/test-art');await page.waitForFunction(()=>window.__scProtectionReady);
 await page.locator('[data-sc-wall-open]').click();if(await page.locator('[data-sc-wall-camera]').isVisible())await page.locator('[data-sc-wall-camera]').click();
 await page.waitForFunction(()=>document.querySelector('[data-sc-wall-camera-video]').readyState>=2);
 assert.equal(await page.locator('[data-sc-wall-camera-video]').evaluate(e=>e.dispatchEvent(new Event('contextmenu',{bubbles:true,cancelable:true}))),false);
 await page.locator('[data-sc-wall-camera-capture]').click();await page.locator('[data-sc-wall-art]').waitFor({state:'visible'});
 assert.equal(await page.locator('[data-sc-wall-sticky-secure]').isEnabled(),true);
 assert.deepEqual(errors,[]);console.log('PASS protected mobile camera launch, video, shutter, artwork and Add to Cart eligibility; no runtime errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
