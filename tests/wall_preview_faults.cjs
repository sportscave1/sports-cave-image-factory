const {chromium}=require('playwright'),assert=require('node:assert/strict');const fixture=require('./wall_preview_completion_fixture.cjs');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
for(const mode of ['denied','unavailable','late-permission','artwork-failure','script-failure']){
 const page=await browser.newPage({viewport:{width:390,height:844},hasTouch:true,userAgent:mode==='artwork-failure'||mode==='script-failure'?'desktop':'iPhone'});let errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(mode=>{window.calls=0;window.stopped=0;if(mode==='unavailable')Object.defineProperty(navigator,'mediaDevices',{value:undefined});else if(mode==='late-permission')navigator.mediaDevices.getUserMedia=()=>{calls++;return new Promise(r=>window.resolveCamera=()=>r({getTracks:()=>[{stop(){stopped++;}}]}));};else if(mode==='denied')navigator.mediaDevices.getUserMedia=async()=>{calls++;throw new DOMException('denied','NotAllowedError');};},mode);
 await page.route('**/*',r=>{if(r.request().url().endsWith('/test')){let body=fixture();if(mode==='script-failure')body=body.replace(/<script>\s*\(function\(\)\{[\s\S]*?<\/script>/,'');return r.fulfill({contentType:'text/html',body:body+'<input aria-label="Search"><button id="normal-cart" onclick="this.textContent=\'Available\'">Normal cart</button>'});}return r.abort();});
 await page.goto('https://www.sportscaveshop.com/test');
 if(mode==='script-failure'){await page.locator('#normal-cart').click();assert.equal(await page.locator('#normal-cart').innerText(),'Available');}
 else{await page.locator('[data-sc-wall-open]').click();
 if(mode==='late-permission'){await page.locator('[data-sc-wall-camera-cancel]').click();await page.evaluate(()=>resolveCamera());await page.waitForFunction(()=>stopped===1);assert(await page.locator('[data-sc-wall-live-camera]').isHidden());}
 else if(mode==='artwork-failure'){await page.locator('[data-sc-wall-upload-input]').setInputFiles('output/image-protection-test-room.jpg');await page.waitForTimeout(500);assert(await page.locator('[data-sc-wall-art]').isHidden());assert(await page.locator('[data-sc-wall-save]').isDisabled());assert(await page.locator('[data-sc-wall-art-error]').isVisible());}
 else{await page.locator('[data-sc-wall-upload]').waitFor({state:'visible'});if(mode==='denied')assert.equal(await page.evaluate(()=>calls),1);}
 await page.keyboard.press('Escape');assert(await page.locator('[data-sc-wall-overlay]').isHidden());
 }
 assert.deepEqual(errors,[],mode);console.log('PASS '+mode);await page.close();
}
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
