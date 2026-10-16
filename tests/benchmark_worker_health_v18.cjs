// Offline fixtures only. Compare the same HTML fixture at 285/334 rows and desktop/mobile.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});const results=[];
try {for(const count of [285,334])for(const width of [1280,390]){
 const runs=[];for(let repetition=0;repetition<3;repetition++){
  const page=await browser.newPage({viewport:{width,height:800}});await page.clock.install();let requests=0;
  const jobs=Array.from({length:count},(_,i)=>({id:'gid://shopify/Product/'+(1800+i),design:'Synthetic artwork '+i,priority:1,stage:'Queued',status:'Queued',category:'Queued',last_activity:'Fixture',attempts:0,checkpoint:'Mapped',actions:[]}));
  await page.route('**/*',route=>{const u=new URL(route.request().url());
   if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync(process.env.WORKER_HEALTH_HTML||'components/worker_health/index.html','utf8')});
   if(u.pathname==='/api/worker-health'){
    requests++;const offset=Number(u.searchParams.get('offset'));const filter=u.searchParams.get('filter');const rows=filter==='Active'?[]:jobs;
    return route.fulfill({json:{overall:'Idle',control:{paused:false},counts:{completed:0,eligible:count,remaining:count,review:0,repair:0,failed:0},progress:{completed:0,total:count},current:null,eta_seconds:null,eta_label:'Calculating',eta_samples:0,last_completed:null,updated_at:'Fixture',revision:'b177b3ea',health:['Render','Companion','Dropbox','Database','Recovery'].map(component=>({component,label:component,status:'Live',reason:''})),warnings:[],filters:{All:count,Active:0,Queued:count,Failed:0,'Needs Review':0,Completed:0},total_rows:rows.length,jobs:rows.slice(offset,offset+25)}});
   }
   if(u.pathname==='/api/worker-health/diagnostics')return route.fulfill({json:{rows:[],next_cursor:null}});
   throw Error('Unexpected request '+u.pathname);
  });
  const start=performance.now();await page.goto('https://v18.local.test/');await page.waitForFunction(()=>!loading&&data!==null);const navigationMs=performance.now()-start;
  assert.equal(await page.locator('#jobs tr[data-id]').count(),25);
  await page.evaluate(()=>{window.jobMutations=0;new MutationObserver(changes=>window.jobMutations+=changes.length).observe(document.getElementById('jobs'),{subtree:true,childList:true,characterData:true});});
  const refresh=[];for(let i=0;i<5;i++){const tick=performance.now();await page.locator('#refresh').click();await page.waitForFunction(()=>!loading);refresh.push(performance.now()-tick);}
  const unchangedMutations=await page.evaluate(()=>window.jobMutations);
  await page.locator('#next').click();await page.waitForFunction(()=>!loading);assert((await page.locator('#page-label').innerText()).startsWith('26'));
  const tick=performance.now();await page.locator('#filter').selectOption('Queued');await page.waitForFunction(()=>!loading);const filterMs=performance.now()-tick;
  const before=requests;await page.evaluate(()=>Object.defineProperty(document,'hidden',{configurable:true,get:()=>true}));await page.clock.runFor(60000);assert.equal(requests,before);
  const cdp=await page.context().newCDPSession(page);await cdp.send('Performance.enable');
  const metric=(r,name)=>r.metrics.find(m=>m.name===name).value;
  const cpuBefore=await cdp.send('Performance.getMetrics');
  await page.evaluate(()=>{for(let i=0;i<100;i++)render(data);});
  const cpuAfter=await cdp.send('Performance.getMetrics');
  const renderScriptMs=(metric(cpuAfter,'ScriptDuration')-metric(cpuBefore,'ScriptDuration'))*1000/100;
  const renderTaskMs=(metric(cpuAfter,'TaskDuration')-metric(cpuBefore,'TaskDuration'))*1000/100;
  const diagnosticsStart=performance.now();await page.evaluate(()=>loadLogs());const diagnosticsMs=performance.now()-diagnosticsStart;
  await cdp.send('HeapProfiler.collectGarbage');const heap=await cdp.send('Runtime.getHeapUsage');
  const nodes=await page.locator('*').count();assert(nodes<500);
  runs.push({navigationMs,refreshMs:refresh,filterMs,diagnosticsMs,renderScriptMs,renderTaskMs,unchangedMutations,domNodes:nodes,heapBytes:heap.usedSize,apiRequests:requests});await page.close();
 }
 results.push({count,width,runs});console.log(JSON.stringify({count,width,runs}));
}fs.mkdirSync('output/v18',{recursive:true});fs.writeFileSync(process.env.WORKER_HEALTH_BENCH_OUTPUT||'output/v18/worker-health-benchmark.json',JSON.stringify(results,null,2));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
