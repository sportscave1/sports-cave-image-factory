// Read-only storefront verification. Camera is mocked; no photo is uploaded.
const {chromium}=require('playwright');
const fs=require('fs'),assert=require('node:assert/strict');
const results=[];
(async()=>{
 for(const channel of ['chrome','msedge']){
  const browser=await chromium.launch({channel,headless:true});
  try{for(const viewport of [{width:1440,height:900},{width:390,height:844}]){
   const context=await browser.newContext({viewport});
   const page=await context.newPage();
   await page.addInitScript(()=>{window.cameraRequests=0;if(navigator.mediaDevices)navigator.mediaDevices.getUserMedia=async()=>{window.cameraRequests++;throw new DOMException('Verification: camera disabled','NotAllowedError');};});
   const base='https://www.sportscaveshop.com/products/peter-brock-tribute-art?variant=52547812589875';
   await page.goto(base+'&sc_wall_preview=1&utm_source=email&utm_campaign=wall-preview-verification',{waitUntil:'domcontentloaded',timeout:60000});
   const heading=page.getByRole('heading',{name:'Take a photo of your wall',exact:true});
   await heading.waitFor({state:'visible',timeout:30000});
   const state=await page.evaluate(()=>({shop:Shopify.shop,theme:Shopify.theme.id,url:location.href,variant:document.querySelector('form[action*="/cart/add"] [name="id"]')?.value,cameraRequests,loader:[...document.scripts].find(s=>s.src.includes('sports-cave-wall-preview-loader'))?.src}));
   assert.equal(state.shop,'sportscave-nb.myshopify.com');assert.equal(state.theme,189389340979);assert.equal(state.variant,'52547812589875');assert.equal(state.cameraRequests,0);
   const url=new URL(state.url);assert.equal(url.searchParams.get('variant'),state.variant);assert.equal(url.searchParams.get('utm_source'),'email');assert.equal(url.searchParams.get('utm_campaign'),'wall-preview-verification');
   for(const sel of ['[data-sc-wall-camera]','[data-sc-wall-upload]','[data-sc-wall-keep-browsing]']){const box=await page.locator(sel).boundingBox();assert(box&&box.x>=0&&box.y>=0&&box.x+box.width<=viewport.width+1&&box.y+box.height<=viewport.height+1);}
   await page.screenshot({path:`artifacts/wall-preview-live-${channel}-${viewport.width}.png`});
   const chooser=page.waitForEvent('filechooser');await page.locator('[data-sc-wall-upload]').click();await chooser;
   await page.locator('[data-sc-wall-camera]').click();assert.equal(await page.evaluate(()=>cameraRequests),1);
   await page.locator('[data-sc-wall-keep-browsing]').click();await heading.waitFor({state:'hidden'});
   await page.locator('[data-sc-wall-preview-trigger]').first().click();await heading.waitFor({state:'visible'});
   await page.locator('[data-sc-wall-keep-browsing]').click();
   await page.goto(base,{waitUntil:'load',timeout:60000});
   assert.equal(await heading.isVisible(),false);assert.equal(await page.evaluate(()=>cameraRequests),0);
   await page.locator('[data-sc-wall-preview-trigger]').first().click();await heading.waitFor({state:'visible'});
   await page.locator('[data-sc-wall-keep-browsing]').click();
   results.push({channel,viewport,status:'PASS',...state});console.log(`PASS live ${channel} ${viewport.width}: auto-open, variant/UTM, viewport, camera opt-in (mock), upload chooser, close/reopen, normal visit/manual`);
   await context.close();
  }}finally{await browser.close();}
 }
 fs.writeFileSync('artifacts/wall-preview-live-verification.json',JSON.stringify(results,null,2));
})().catch(e=>{console.error(e);process.exit(1);});
