// Loopback-only real Streamlit frontend. Never contact business APIs.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage(),errors=[],assets=[];page.setDefaultTimeout(60000);
 page.on('pageerror',e=>errors.push(e.message));
 page.on('response',async r=>{if(/\/static\/(js|css)\//.test(r.url()))assets.push({url:new URL(r.url()).pathname,encoding:r.headers()['content-encoding']||'identity',bytes:Number(r.headers()['content-length']||0)});});
 const cdp=await context.newCDPSession(page);
 const transfers=new Map();await cdp.send('Network.enable');
 cdp.on('Network.responseReceived',e=>{if(/\/static\/(js|css)\//.test(e.response.url))transfers.set(e.requestId,{url:new URL(e.response.url).pathname,bytes:0});});
 cdp.on('Network.loadingFinished',e=>{if(transfers.has(e.requestId))transfers.get(e.requestId).bytes=e.encodedDataLength;});
 if(process.env.PERF_SLOW){await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:150,downloadThroughput:200000,uploadThroughput:100000});}
 let t=Date.now();await page.goto('http://127.0.0.1:8555/');await page.getByTestId('stMetric').first().waitFor();await page.getByTestId('stDataFrame').first().waitFor();
 const result={coldHomeMs:Date.now()-t};
 async function profile(){let prior=await page.locator('#phase2-profile').innerText();await page.getByRole('button',{name:'Read profile',exact:true}).click();await page.waitForFunction(s=>document.querySelector('#phase2-profile')?.textContent!==s,prior);return JSON.parse(await page.locator('#phase2-profile').innerText());}
 result.initial=await profile();
 result.assets=assets.slice();result.assetBytes=[...transfers.values()].reduce((a,r)=>a+r.bytes,0);
 const perf=await cdp.send('Performance.enable');result.navigation=await page.evaluate(()=>{const n=performance.getEntriesByType('navigation')[0];return {ttfb:n.responseStart-n.requestStart,domContentLoaded:n.domContentLoadedEventEnd,resources:performance.getEntriesByType('resource').length}});
 await page.getByText('Other',{exact:true}).click();await page.getByText('Other page ready',{exact:true}).waitFor();
 t=Date.now();await page.getByText('Home',{exact:true}).click();await page.getByTestId('stMetric').first().waitFor();result.warmHomeMs=Date.now()-t;result.warm=await profile();assert.equal(result.warm.weekly_reads,1);
 await page.getByRole('button',{name:'Refresh weekly fixture',exact:true}).click();
 await page.waitForFunction(()=>[...document.querySelectorAll('[data-testid="stMetric"]')].some(m=>m.textContent.includes('Tasks completed')&&m.querySelector('[data-testid="stMetricValue"]')?.textContent==='2'));
 result.refreshed=await profile();assert.equal(result.refreshed.weekly_reads,2);
 await page.getByText('Analytics',{exact:true}).click();await page.getByRole('tab',{name:'Top pages',exact:true}).waitFor();await page.getByTestId('stDataFrame').first().waitFor();
 result.tabs=[];
 for(const name of ['Channels','Countries','Devices','Top pages','Channels']){
  t=Date.now();await page.getByRole('tab',{name,exact:true}).click();await page.locator('[data-baseweb="tab-panel"]:visible [data-testid="stDataFrame"]').waitFor();result.tabs.push({name,visibleMs:Date.now()-t});await profile();
 }
 result.final=await profile();assert.equal(result.final.analytics_reads,4);
 // Rapidly leave a requested Home refresh. Its fragment must not reopen Home.
 await page.getByText('Home',{exact:true}).click();await page.getByTestId('stMetric').first().waitFor();
 await page.getByRole('button',{name:'Refresh weekly fixture',exact:true}).click();
 await page.getByText('Other',{exact:true}).click();await page.getByText('Other page ready',{exact:true}).waitFor();
 await profile();assert.equal(await page.getByTestId('stMetric').count(),0);
 await page.getByText('Home',{exact:true}).click();await page.getByTestId('stMetric').first().waitFor();await page.setViewportSize({width:650,height:850});
 await page.waitForFunction(()=>{const s=document.querySelector('[data-testid="stSidebar"]');return !s||s.getBoundingClientRect().right<1||getComputedStyle(s).display==='none'});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
 assert.equal(await page.getByTestId('stException').count(),0);assert.deepEqual(errors,[]);
 result.heap=(await cdp.send('Performance.getMetrics')).metrics.filter(x=>['JSHeapUsedSize','TaskDuration','LayoutCount'].includes(x.name));
 fs.mkdirSync('.tmp-phase2-results',{recursive:true});fs.writeFileSync(`.tmp-phase2-results/browser-${process.env.PHASE2_BASELINE?'before':'after'}${process.env.PERF_SLOW?'-slow':''}.json`,JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 await page.screenshot({path:`.tmp-phase2-results/home-${process.env.PHASE2_BASELINE?'before':'after'}-narrow.png`,fullPage:true});
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
