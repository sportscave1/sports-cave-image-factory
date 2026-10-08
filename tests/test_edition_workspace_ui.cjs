const {chromium}=require('playwright');const assert=require('node:assert/strict');const fs=require('node:fs');fs.mkdirSync('.tmp-edition-evidence',{recursive:true});
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 if(process.env.EDITION_SLOW==='1'){const cdp=await context.newCDPSession(page);await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});await cdp.send('Network.enable');await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:100,downloadThroughput:200000,uploadThroughput:100000});}
 const baseline=process.env.EDITION_BASELINE==='1',url=process.env.EDITION_URL||'http://127.0.0.1:8895';
 const start=Date.now();await page.goto(url);await page.getByTestId('stDataFrame').waitFor();const results={initialMs:Date.now()-start};
 async function read(){const prior=await page.locator('#edition-profile').textContent();await page.getByRole('button',{name:'Profile snapshot',exact:true}).click();await page.waitForFunction(p=>document.querySelector('#edition-profile')?.textContent!==p,prior);return JSON.parse(await page.locator('#edition-profile').textContent());}
 const before=await read();let t=Date.now();
 await page.evaluate(()=>{window.editionFrames=[];window.editionSampling=true;function frame(){if(!window.editionSampling)return;window.editionFrames.push({tables:document.querySelectorAll('[data-testid="stDataFrame"]').length,largestIcon:Math.max(0,...[...document.querySelectorAll('[data-testid="stMain"] svg')].map(e=>e.getBoundingClientRect().height))});requestAnimationFrame(frame)}requestAnimationFrame(frame)});
 await page.getByTestId('stSelectbox').filter({hasText:'Find product'}).getByRole('combobox').fill('Artwork 050');
 await page.getByRole('option',{name:/Artwork 050/}).click();await page.getByTestId('stDataFrame').waitFor();const after=await read();
 results.search={ms:Date.now()-t,fullRuns:after.full_runs-before.full_runs,loads:after.loads-before.loads};
 const frames=await page.evaluate(()=>{window.editionSampling=false;return window.editionFrames});results.sampledSearchFrames=frames.length;
 if(!baseline){assert.ok(frames.every(f=>f.tables===1));assert.ok(frames.every(f=>f.largestIcon<=64));}
 if(!baseline){
  assert.equal(results.search.fullRuns,0);assert.equal(results.search.loads,0);assert.equal(after.archive,before.archive);
  t=Date.now();await page.getByRole('button',{name:'Start New Edition Version',exact:true}).click();await page.getByRole('dialog').waitFor();results.dialogMs=Date.now()-t;
  const dialog=page.getByRole('dialog');await dialog.getByRole('textbox',{name:'Design revision reason'}).fill('Revised collector artwork');
  await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});assert.equal((await read()).full_runs,after.full_runs);
  t=Date.now();await page.getByText('Expired Editions',{exact:true}).click();await page.getByText('No expired editions.',{exact:true}).waitFor();const archiveMs=Date.now()-t;const archived=await read();results.archive={ms:archiveMs,fullRuns:archived.full_runs-after.full_runs};assert.equal(results.archive.fullRuns,0);
 }
 const route=page.getByTestId('stSidebar').getByRole('combobox');await route.click();await page.getByRole('option',{name:'Home',exact:true}).click();await page.getByTestId('stMain').getByText('Home',{exact:true}).waitFor();
 t=Date.now();await route.click();await page.getByRole('option',{name:'Edition Ops',exact:true}).click();await page.getByTestId('stDataFrame').waitFor();results.warmReturnMs=Date.now()-t;
 if(!baseline){for(const width of [1000,750,390]){await page.setViewportSize({width,height:1000});await page.waitForFunction(()=>{const e=document.querySelector('[data-testid="stMain"]');return e.scrollWidth<=e.clientWidth+2});}}
 await page.setViewportSize({width:1440,height:1000});await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));await page.screenshot({path:'.tmp-edition-evidence/edition-'+(baseline?'before':'after')+'.png',fullPage:true});
 assert.equal(await page.getByTestId('stException').count(),0);assert.deepEqual(errors,[]);
 fs.writeFileSync('.tmp-edition-evidence/edition-'+(baseline?'before':'after')+'.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
