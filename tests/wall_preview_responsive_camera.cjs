const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('fs');
const fixture=require('./wall_preview_completion_fixture.cjs');
const sizes=[[320,568],[360,640],[375,667],[375,812],[390,844],[393,852],[412,915],[430,932],[568,320],[667,375],[844,390],[932,430],[768,1024],[820,1180],[1024,1366],[1280,720],[1366,768],[1440,900],[1920,1080],[2560,1440]];
(async()=>{
 const browser=await chromium.launch({channel:process.env.SC_BROWSER||'chrome',headless:true,args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']});let count=0;
 try{for(const [width,height] of sizes){
  const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:width<1000?3:1,hasTouch:true,userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1',permissions:['camera']});let errors=[],before=0;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>{const u=r.request().url();if(u.endsWith('/test'))return r.fulfill({contentType:'text/html',body:fixture()});if(u.endsWith('/art.png')){before++;return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="500" height="500"><rect width="500" height="500" fill="navy"/></svg>'});}return r.abort();});
  await page.goto('https://www.sportscaveshop.com/test');assert.equal(before,0,'artwork lazy until open');
  await page.locator('[data-sc-wall-open]').click();await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
  async function controls(){const result=await page.evaluate(()=>['camera-capture','camera-library','camera-cancel'].map(s=>{const e=document.querySelector('[data-sc-wall-'+s+']'),r=e.getBoundingClientRect();return {s,x:r.x,y:r.y,right:r.right,bottom:r.bottom,w:r.width,h:r.height,hit:e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))};}));assert(result.every(r=>r.x>=0&&r.y>=0&&r.right<=width+1&&r.bottom<=height+1&&r.w>=44&&r.h>=44&&r.hit),JSON.stringify({width,height,result}));assert(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth));}
  await controls();
  // Simulate browser chrome reducing the visual viewport; no polling needed.
  await page.evaluate(async()=>{if(document.fullscreenElement)await document.exitFullscreen();const vv=window.visualViewport;Object.defineProperty(vv,'height',{configurable:true,value:Math.max(180,innerHeight-100)});vv.dispatchEvent(new Event('resize'));});await page.waitForTimeout(60);
  assert(await page.locator('[data-sc-wall-camera-capture]').evaluate(e=>e.getBoundingClientRect().bottom<=visualViewport.height+1),'capture survives toolbar expansion');
  await page.locator('[data-sc-wall-camera-cancel]').click();assert(await page.locator('video').evaluate(e=>e.srcObject===null));
  await page.keyboard.press('Escape');assert(await page.locator('[data-sc-wall-overlay]').isHidden());
  await page.locator('[data-sc-wall-open]').click();await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
  await page.locator('[data-sc-wall-camera-capture]').click();await page.locator('[data-sc-wall-quick-preview]').click();await page.locator('[data-sc-wall-art]').waitFor({state:'visible'});await page.waitForFunction(()=>document.querySelector('video').srcObject===null);
  assert.deepEqual(errors,[]);count++;console.log('PASS camera '+width+'x'+height);await page.close();
 }
 // Denial must use a clear upload fallback without repeated permission attempts.
 const page=await browser.newPage({viewport:{width:390,height:844},hasTouch:true,userAgent:'iPhone'});
 await page.addInitScript(()=>{window.cameraRequests=0;navigator.mediaDevices.getUserMedia=async()=>{window.cameraRequests++;throw new DOMException('Denied','NotAllowedError');};});
 await page.route('**/*',r=>r.request().url().endsWith('/test')?r.fulfill({contentType:'text/html',body:fixture()}):r.abort());await page.goto('https://www.sportscaveshop.com/test');await page.locator('[data-sc-wall-open]').click();await page.locator('[data-sc-wall-upload]').waitFor({state:'visible'});assert.equal(await page.evaluate(()=>cameraRequests),1);await page.keyboard.press('Escape');assert(await page.locator('[data-sc-wall-overlay]').isHidden());await page.close();
 console.log(`${count} camera viewports plus denial recovery passed`);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
