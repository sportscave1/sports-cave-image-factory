const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{for(const width of [1280,390]){
 const page=await browser.newPage({viewport:{width,height:800}});let reads=0,logReads=0,paused=false,active=true,unavailable=false;const controls=[],queries=[];
 const diagnostic={id:71,trace:'AE-71',timestamp:'16 Oct 2026 07:00:00 AEDT',component:'Photoshop',design:'Synthetic artwork',description:'Photoshop export failed — ICC profile mismatch.',code:'ICC_MISMATCH',stage:'Preparing',attempts:1,last_checkpoint:'claimed',revision:'abcdef12',recovery_attempted:false,recommended_action:'Review colour profile evidence.'};
 const all=Array.from({length:334},(_,i)=>({id:'gid://shopify/Product/'+(1000+i),design:'Synthetic artwork '+i,priority:i?1:8,stage:i?'Claimed':'Uploading',status:i?'Queued':'Uploading',category:i?'Queued':'Active',elapsed_seconds:i?null:30,last_activity:'16 Oct 2026 07:00:00 AEDT',checkpoint:'Claimed',attempts:1,actions:[]}));
 await page.clock.install();await page.route('**/*',route=>{const url=new URL(route.request().url());
  if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/worker_health/index.html','utf8')});
  if(url.pathname==='/api/worker-health/control'){const body=route.request().postDataJSON();assert.deepEqual(Object.keys(body),['paused']);paused=body.paused;controls.push(paused);return route.fulfill({json:{paused,state:paused&&active?'Pausing':paused?'Paused':'Resumed'}});}
  if(url.pathname==='/api/worker-health/diagnostics'){logReads++;queries.push(url.searchParams);return route.fulfill({json:{rows:[diagnostic],next_cursor:null}});}
  if(url.pathname==='/api/worker-health'){reads++;if(unavailable)return route.fulfill({status:503,json:{error:'Authoritative worker status unavailable.',trace:'WH-fixture'}});
   const filter=url.searchParams.get('filter');assert(['All','Active','Queued','Failed','Needs Review','Completed'].includes(filter));const offset=Number(url.searchParams.get('offset'));let jobs=all.filter(j=>filter==='All'||j.category===filter);
   return route.fulfill({json:{overall:paused?(active?'Pausing':'Paused'):'Live',control:{paused},counts:{completed:61,eligible:285,remaining:110,review:45,repair:41,failed:72},progress:{completed:61,total:285,ratio:61/285,current_job_ratio:null},current:active?all[0]:null,eta_seconds:paused?null:600,eta_label:paused?'Paused':'Estimated runnable backlog',eta_samples:5,last_completed:{design:'Verified artwork',at:diagnostic.timestamp},updated_at:diagnostic.timestamp,revision:'abcdef12',health:['Render','Companion','Dropbox','Database','Recovery'].map(component=>({component,label:component,status:'Live',last_seen:diagnostic.timestamp,reason:''})),warnings:[],filters:{All:334,Active:1,Queued:333,Failed:0,'Needs Review':0,Completed:0},total_rows:jobs.length,jobs:jobs.slice(offset,offset+25)}});}
  if(url.pathname==='/auto-editions/status')return route.fulfill({contentType:'text/html',body:'<label><input id="confirm" type="checkbox">Existing visual review</label>'});
  throw Error('Unexpected provider or page request: '+url.pathname);
 });
 const started=Date.now();await page.goto('https://health.local.test/');await page.getByText('Verified artwork',{exact:false}).waitFor();const firstPaintMs=Date.now()-started;
 assert.equal(reads,1);assert.equal(logReads,0);assert.equal(await page.locator('#jobs tr[data-id]').count(),25);
 assert.equal(await page.locator('#job-progress').getAttribute('value'),null);assert.equal(await page.locator('#backlog-progress').getAttribute('value'),'61');
 const row=page.locator('#jobs tr[data-id]').first();assert((await row.boundingBox()).height<=32);
 await row.click();await page.getByText('AE-71',{exact:false}).first().waitFor();assert.equal(logReads,1);
 await page.locator('#jobs-pane').evaluate(el=>el.scrollTop=180);const scroll=await page.locator('#jobs-pane').evaluate(el=>el.scrollTop);
 await page.clock.runFor(20100);await page.waitForFunction(()=>!loading);assert.equal(reads,2);
 assert.equal(await page.locator('tr.details').count(),1);assert.equal(await page.locator('#jobs-pane').evaluate(el=>el.scrollTop),scroll);
 await page.getByRole('button',{name:'Pause',exact:true}).click();await page.getByText('Pausing',{exact:true}).waitFor();assert.deepEqual(controls,[true]);
 active=false;await page.clock.runFor(20100);await page.waitForFunction(()=>!loading);assert.equal(await page.locator('#overall').innerText(),'Paused');
 await page.getByRole('button',{name:'Resume',exact:true}).click();await page.getByText('Live',{exact:true}).first().waitFor();assert.deepEqual(controls,[true,false]);
 await page.locator('tr.details button').click();const dialog=page.locator('#action-dialog');assert(await dialog.isVisible());await page.frameLocator('#action-dialog iframe').locator('#confirm').check();
 await page.clock.runFor(20100);await page.waitForFunction(()=>!loading);assert(await page.frameLocator('#action-dialog iframe').locator('#confirm').isChecked());
 await page.locator('#close-dialog').click();await page.locator('#filter').selectOption('Queued');await page.waitForFunction(()=>!loading);assert.equal(await page.locator('#filter').inputValue(),'Queued');
 await page.locator('#next').click();await page.waitForFunction(()=>!loading);assert((await page.locator('#page-label').innerText()).startsWith('26'));
 await page.locator('#logs-panel summary').first().click();await page.locator('#log-search').fill('ICC');await page.locator('#component').selectOption('Photoshop');await page.locator('#date-from').fill('2026-10-16');await page.locator('#log-refresh').click();await page.waitForFunction(()=>logsLoaded);
 assert(queries.some(q=>q.get('component')==='Photoshop'&&q.get('search')==='ICC'&&q.get('date_from')==='2026-10-16'));
 fs.mkdirSync('output/worker-health',{recursive:true});await page.locator('#logs-panel summary').first().click();await page.screenshot({path:`output/worker-health/healthy-${width}.png`});
 const session=await page.context().newCDPSession(page);await session.send('HeapProfiler.collectGarbage');const beforeHeap=await session.send('Runtime.getHeapUsage');const nodeCount=await page.locator('*').count();const stable=await page.locator('#jobs tr[data-id]').first().elementHandle();
 for(let n=0;n<10;n++){await page.clock.runFor(20050);await page.waitForFunction(()=>!loading);}
 await session.send('HeapProfiler.collectGarbage');const afterHeap=await session.send('Runtime.getHeapUsage');assert.equal(await page.locator('*').count(),nodeCount);assert(await stable.evaluate(el=>el.isConnected));assert(afterHeap.usedSize-beforeHeap.usedSize<1024*1024);
 console.log(JSON.stringify({width,firstPaintMs,initialSnapshotReads:1,initialDiagnosticReads:0,rowsRendered:25,rowHeight:30,refreshes:10,domNodes:nodeCount,retainedHeapBefore:beforeHeap.usedSize,retainedHeapAfter:afterHeap.usedSize}));
 unavailable=true;await page.locator('#refresh').click();await page.getByText('Unavailable',{exact:true}).waitFor();assert.equal(await page.locator('#completed').innerText(),'61');assert(await page.locator('#pause').isDisabled());assert.equal(await page.locator('#log-search').inputValue(),'ICC');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 fs.mkdirSync('output/worker-health',{recursive:true});await page.screenshot({path:`output/worker-health/page-${width}.png`});
 await page.close();console.log(`Worker Health ${width}: measured progress, 20s refresh, safe controls, inline details/dialog state, paging, diagnostics and unavailable state passed`);
 }}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
