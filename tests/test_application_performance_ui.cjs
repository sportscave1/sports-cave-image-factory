// Real Chromium + production Analytics components; strictly offline fixture.
const {chromium}=require('playwright'), fs=require('node:fs'), assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage(), errors=[];
  page.setDefaultTimeout(15000);
  page.on('pageerror',e=>errors.push(e.message));
  if(process.env.PERF_SLOW){const cdp=await context.newCDPSession(page);await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:150,downloadThroughput:200000,uploadThroughput:100000});}
  const start=Date.now();await page.goto('http://127.0.0.1:8551/'+(process.env.PERF_BASELINE?'?baseline=1':''));await page.locator('#performance-profile').waitFor();
  await page.waitForFunction(()=>document.querySelectorAll('[data-testid=stMetric]').length>=8);
  const result={coldMs:Date.now()-start};
  async function profile(){const previous=await page.locator('#performance-profile').innerText();await page.getByRole('button',{name:'Read profile',exact:true}).click();await page.waitForFunction(old=>document.querySelector('#performance-profile')?.textContent!==old,previous);return JSON.parse(await page.locator('#performance-profile').innerText());}
  result.initial=await profile();
  await page.evaluate(()=>{window.metricNode=document.querySelector('[data-testid=stMetric]');window.frames=[];window.sampling=true;function tick(){if(!window.sampling)return;window.frames.push({metrics:document.querySelectorAll('[data-testid=stMetric]').length,exceptions:document.querySelectorAll('[data-testid=stException]').length});requestAnimationFrame(tick)}tick()});
  result.tabs=[];
  for(const name of ['Channels','Countries','Devices','Top pages','Channels']){
   const before=await profile(),t=Date.now();await page.getByRole('tab',{name,exact:true}).click();
   await page.getByRole('tabpanel').filter({visible:true}).locator('[data-testid=stDataFrame]').waitFor();
   const after=await profile();result.tabs.push({name,ms:Date.now()-t,reads:after.queries.length-before.queries.length,fullRuns:after.full_runs-before.full_runs});
  }
  result.metricNodePreserved=await page.evaluate(()=>window.metricNode===document.querySelector('[data-testid=stMetric]'));
  result.frames=await page.evaluate(()=>{window.sampling=false;return {count:window.frames.length,missing:window.frames.filter(f=>f.metrics===0).length,exceptions:window.frames.filter(f=>f.exceptions).length}});
  await page.getByText('Other page',{exact:true}).click();await page.getByText('Other page ready',{exact:true}).waitFor();
  const warm=Date.now();await page.getByText('Analytics',{exact:true}).click();await page.getByText('Store orders',{exact:true}).waitFor();result.warmMs=Date.now()-warm;
  await page.setViewportSize({width:650,height:850});await page.getByRole('tab',{name:'Devices',exact:true}).click();await profile();
  result.horizontalOverflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2);
  if(!process.env.PERF_BASELINE){
   await page.getByText('Reporting',{exact:true}).click();await page.getByRole('textbox',{name:'Staff',exact:true}).waitFor();
   const before=await profile();await page.getByRole('textbox',{name:'Staff',exact:true}).fill('offline');await page.getByRole('textbox',{name:'Staff',exact:true}).press('Enter');
   const after=await profile();result.archiveFilterFullRuns=after.full_runs-before.full_runs;
   assert.equal(result.archiveFilterFullRuns,0);
  }
  assert.deepEqual(errors,[]);assert.equal(await page.locator('[data-testid=stException]').count(),0);
  if(!process.env.PERF_BASELINE){assert.equal(result.initial.queries.length,5);assert.ok(result.tabs.every(t=>t.reads<=1&&t.fullRuns===0));assert.equal(result.tabs.at(-1).reads,0);assert.equal(result.metricNodePreserved,true);assert.equal(result.frames.exceptions,0);assert.equal(result.frames.missing,0);assert.equal(result.horizontalOverflow,false);}
  fs.mkdirSync('.tmp-performance-results',{recursive:true});fs.writeFileSync(`.tmp-performance-results/application-performance-${process.env.PERF_BASELINE?'before':'after'}${process.env.PERF_SLOW?'-slow':''}.json`,JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
