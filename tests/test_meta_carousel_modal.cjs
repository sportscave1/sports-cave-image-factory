const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{fs.mkdirSync('.tmp-meta-carousel',{recursive:true});const browser=await chromium.launch({channel:'chrome',headless:true});try{
for(const [width,height] of [[1920,1080],[1440,900],[1366,768],[1024,768],[430,932],[390,844]]){
 const page=await browser.newPage({viewport:{width,height}});page.setDefaultTimeout(15000);
 await page.route('**/*',r=>{const u=new URL(r.request().url());if(/\/thumb\/\d.png/.test(u.pathname))return r.fulfill({contentType:'image/png',body:fs.readFileSync(`tests/fixtures/meta_carousel_cards/card${u.pathname.match(/(\d).png/)[1]}.png`)});return u.hostname==='127.0.0.1'?r.continue():r.abort();});
 await page.goto('http://127.0.0.1:8533');await page.getByRole('button',{name:'Open campaign fixture'}).click();
 const dialog=page.getByRole('dialog');await dialog.waitFor();const strip=dialog.frameLocator('iframe').first();await strip.locator('.card').nth(3).waitFor();
 assert.equal(await strip.locator('.card').count(),4);assert.equal(await dialog.getByText('Winner to use',{exact:true}).count(),0);assert.equal(await dialog.getByText('Diagnostics',{exact:true}).count(),0);
 const apply=dialog.getByRole('button',{name:'APPLY TO CREATIVE REFRESH',exact:true});assert(await apply.isEnabled());
 const bounds=await dialog.boundingBox();assert(bounds.width<=Math.min(width,1400));assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.equal(await page.getByTestId('stException').count(),0);await apply.click();await dialog.getByRole('link',{name:'OPEN CREATIVE REFRESH',exact:true}).waitFor();
 await page.screenshot({path:`.tmp-meta-carousel/ux-modal-${width}.png`});console.log(JSON.stringify({width,height,modalWidth:bounds.width,allCards:true,manualSelection:true,apply:true}));await page.close();
}}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
