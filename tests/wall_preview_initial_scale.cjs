const {chromium}=require('playwright'),assert=require('node:assert/strict');
const fixture=require('./wall_preview_completion_fixture.cjs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true,args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']});let passed=0;
 try{for(const [width,height,camera] of [[1366,768,false],[390,844,false],[667,375,false],[390,844,true]]){
  for(const decision of ['skip','close','scale']){
   const page=await browser.newPage({viewport:{width,height},hasTouch:camera,userAgent:camera?'iPhone':'desktop',permissions:['camera']});const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/*',r=>r.request().url().endsWith('/test')?r.fulfill({contentType:'text/html',body:fixture()}):r.request().url().endsWith('/art.png')?r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000"><rect width="1000" height="1000" fill="navy"/></svg>'}):r.abort());
   await page.goto('https://www.sportscaveshop.com/test');await page.locator('[data-sc-wall-open]').click();
   await page.evaluate(()=>{window.earlyArt=false;window.decided=false;const art=document.querySelector('[data-sc-wall-art]');new MutationObserver(()=>{if(!window.decided&&!art.hidden&&art.getClientRects().length)window.earlyArt=true;}).observe(art,{attributes:true});});
   if(camera){await page.waitForFunction(()=>document.querySelector('video').readyState>=2);await page.locator('[data-sc-wall-camera-capture]').click();}
   else{const data=await page.evaluate(()=>{let c=document.createElement('canvas');c.width=innerWidth>innerHeight?1200:900;c.height=innerWidth>innerHeight?900:1200;return c.toDataURL().split(',')[1];});await page.locator('[data-sc-wall-upload-input]').setInputFiles({name:'room.png',mimeType:'image/png',buffer:Buffer.from(data,'base64')});}
   const help=page.locator('[data-sc-wall-scale-help]'),art=page.locator('[data-sc-wall-art]');await help.waitFor({state:'visible'});
   await page.waitForFunction(()=>document.querySelector('[data-sc-wall-room]').naturalWidth>0);
   assert.equal(await help.count(),1);assert(await art.isHidden());assert.equal(await page.evaluate(()=>earlyArt),false);
   await page.evaluate(()=>{window.decided=true;});
   if(decision==='scale'){
    // Exercise the existing two-point calculation and measurement submission.
    await page.locator('[data-sc-wall-stage]').evaluate(e=>{let r=e.getBoundingClientRect();for(const x of [.2,.7])e.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,clientX:r.x+r.width*x,clientY:r.y+r.height*.2,button:0}));});
    await page.locator('[data-sc-wall-reference-measurement]').fill('100');await page.locator('[data-sc-wall-submit-measurement]').click();
   }else await page.locator(decision==='skip'?'[data-sc-wall-quick-preview]':'[data-sc-wall-scale-help-close]').click();
   await art.waitFor({state:'visible'});assert(await help.isHidden());
   assert.equal(await page.locator('[data-sc-wall-quick-badge]').isVisible(),decision!=='scale');
   if(decision!=='scale'){
    await page.locator('[data-sc-wall-set-real-scale]').click();await help.waitFor({state:'visible'});assert(await art.isHidden());
    await page.locator('[data-sc-wall-scale-help-close]').click();assert(await art.isHidden(),'later help-close keeps existing point-selection behaviour');
    await page.locator('[data-sc-wall-scale-help-reopen]').click();await page.locator('[data-sc-wall-quick-preview]').click();await art.waitFor({state:'visible'});
   }
   assert.deepEqual(errors,[]);console.log('PASS',width,height,camera?'camera':'upload',decision);passed++;await page.close();
  }
 } }finally{await browser.close();}
 console.log(passed+' initial scale journeys passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
