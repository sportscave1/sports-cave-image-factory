// Identical synthetic native fixtures; baseline modules are committed V14.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});const results=[];
 try{for(const width of [1440,390])for(const [label,port] of [['V14',8646],['V15',8645]])for(let run=0;run<3;run++){
  const page=await browser.newPage({viewport:{width,height:900}});let calls=0;
  page.on('request',r=>{if(r.url().endsWith('/api/auto-editions/status'))calls++;});
  const started=Date.now();await page.goto(`http://127.0.0.1:${port}`);
  await page.locator('[data-testid=stDataFrame] canvas').first().waitFor();
  const renderMs=Date.now()-started;await page.waitForTimeout(250);
  const cdp=await page.context().newCDPSession(page);await cdp.send('Performance.enable');
  await cdp.send('HeapProfiler.collectGarbage');
  const metrics=async()=>Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map(m=>[m.name,m.value]));
  const before=await metrics();
  if(label==='V15'){
   await page.waitForFunction(()=>!!window.SportsCaveEditionStatus);
   for(let n=0;n<30;n++)await page.evaluate(n=>{
    const f=[...document.querySelectorAll('iframe')].find(f=>f.title?.includes('edition_auto_live'));
    f.contentWindow.Date.now=()=>new Date().getTime()+(n+1)*25000;
    return SportsCaveEditionStatus.poll();
   },n);
   assert.equal(calls,30,'One batched read for each simulated visible interval');
   assert((await page.locator('body').innerText()).includes('fixture-main-runs: 1'));
  }
  await cdp.send('HeapProfiler.collectGarbage');const after=await metrics();
  if(label==='V15'){
   for(let n=30;n<60;n++)await page.evaluate(n=>{
    const f=[...document.querySelectorAll('iframe')].find(f=>f.title?.includes('edition_auto_live'));
    f.contentWindow.Date.now=()=>new Date().getTime()+(n+1)*25000;
    return SportsCaveEditionStatus.poll();
   },n);
   await cdp.send('HeapProfiler.collectGarbage');
  }
  const final=await metrics();
  assert(final.JSHeapUsedSize-after.JSHeapUsedSize<1024*1024,'Unchanged polling must not accumulate a new table per batch');
  results.push({label,width,run,products:334,render_ms:renderMs,js_heap_bytes:before.JSHeapUsedSize,
    heap_after_30_polls_bytes:after.JSHeapUsedSize,heap_after_60_polls_bytes:final.JSHeapUsedSize,dom_nodes:after.Nodes,requests:calls,
    grid_height:await page.locator('[data-testid=stDataFrame]').evaluate(n=>n.getBoundingClientRect().height)});
  await page.close();
 }
 fs.mkdirSync('output/v15-phase3',{recursive:true});fs.writeFileSync('output/v15-phase3/browser-performance.json',JSON.stringify(results,null,2));
 console.log(JSON.stringify(results));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
