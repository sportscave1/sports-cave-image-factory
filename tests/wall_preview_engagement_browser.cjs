// Real viewer + mocked first-party endpoint only. No production writes.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fixture=require('./wall_preview_completion_fixture.cjs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']});
 try{for(const camera of [false,true]){
  const page=await browser.newPage({viewport:camera?{width:390,height:844}:{width:1366,height:768},hasTouch:camera,userAgent:camera?'iPhone':'desktop',permissions:['camera']});let events=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async r=>{const u=r.request().url();
   if(u.includes('/analytics/events')){if(r.request().method()==='POST')events.push(JSON.parse(r.request().postData()));return r.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:'{"ok":true}'});}
   if(u.includes('/api/wall-previews'))return r.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'},body:'{"ok":true,"archive_status":"queued"}'});
   if(u.endsWith('/cart.js'))return r.fulfill({contentType:'application/json',body:'{"items":[],"item_count":1}'});
   if(u.includes('/cart/add.js'))return r.fulfill({contentType:'application/json',body:'{"id":456,"sections":{}}'});
   if(u.endsWith('/art.png'))return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000"><rect width="1000" height="1000" fill="navy"/></svg>'});
   if(u.endsWith('/test'))return r.fulfill({contentType:'text/html',body:fixture()});return r.abort();
  });
  await page.goto('https://www.sportscaveshop.com/test');await page.locator('[data-sc-wall-open]').click();
  if(camera){await page.waitForFunction(()=>document.querySelector('video').readyState>=2);await page.locator('[data-sc-wall-camera-capture]').click();}
  else{const b=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=900;c.height=1200;return c.toDataURL().split(',')[1];});await page.locator('[data-sc-wall-upload-input]').setInputFiles({name:'room.png',mimeType:'image/png',buffer:Buffer.from(b,'base64')});}
  await page.waitForFunction(()=>document.querySelector('[data-sc-wall-room]').naturalWidth>0);
  await page.locator('[data-sc-wall-quick-preview]').click();const art=page.locator('[data-sc-wall-art]');await art.waitFor({state:'visible'});
  const box=await art.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+15,box.y+box.height/2+10);await page.mouse.up();await page.locator('[data-sc-wall-confirm]').click();
  await page.waitForFunction(()=>document.querySelector('[data-sc-wall-confirm-label]').textContent.includes('Your wall preview is ready'));
  await page.locator('[data-sc-wall-sticky-secure]').click();await page.locator('[data-sc-wall-close]').first().click();
  await page.waitForTimeout(150);const names=events.map(e=>e.event);
  for(const name of ['cta_click','open','photo_loaded','placement_confirmed','add_to_cart','close',...(camera?['camera_open']:[])])assert.equal(names.filter(n=>n==='wall_preview_'+name).length,1,name);
  assert.equal(new Set(events.map(e=>e.wall_preview_session_id)).size,1);assert.equal(new Set(events.map(e=>e.event_id)).size,events.length);
  assert.equal(errors.length,0,errors.join());assert(events.filter(e=>e.event==='wall_preview_photo_loaded').every(e=>e.capture_source===(camera?'camera':'upload')));
  console.log('PASS real viewer '+(camera?'mobile camera':'desktop upload')+': complete funnel, ATC before archive, close beacon; no errors');await page.close();
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
