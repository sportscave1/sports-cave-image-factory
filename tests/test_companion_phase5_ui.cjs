const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{for(const width of [1280,390]){
 const page=await browser.newPage({viewport:{width,height:850}});let cap=3,phase='Uploading',resumable=false,command=null,ack=false,attention=null;
 const settings={mode:'Maximum speed',manual_mbps:null,sustainable_mbps:null,headroom_percent:25,background_percent:25,download_mbps:null,paused:false};
 const state=()=>({instance:'a'.repeat(24),age_seconds:1,requested:command,attention,effective:{capability:cap,revision:ack?command.revision:'request_5670',settings:ack?command.settings:settings,effective_mbps:ack?4:null,protection:ack?'Limited':'Maximum speed (uncapped)',pause_state:phase==='Paused'?'Paused at chunk boundary':'Running',active_upload:phase!=='Cloud Ready',active_download:false,calibration:{state:'Calibration needed',source:'Unmeasured',sustainable_mbps:null,sample_count:0,adaptive_percent:100},transfer:{state:phase,resumable,transport_bytes:65536,total_bytes:131072,payload_bytes_per_second:32768,eta_seconds:999}}});
 const summary=()=>({overall:'Idle',current:null,updated_at:'Fixture',counts:{completed:1,eligible:30,remaining:0,review:0,repair:0,failed:28},progress:{completed:1,total:30},control:{paused:false},health:[],warnings:[],filters:{All:0},revision:'local',transfer_control:state()});
 await page.route('**/*',route=>{const url=new URL(route.request().url());
  if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/worker_health/index.html','utf8')});
  if(url.pathname==='/api/worker-health/control'){command={revision:'request_5671',settings:route.request().postDataJSON().transfer_settings};return route.fulfill({json:{requested:command}});}
  if(['/api/worker-health/jobs','/api/worker-health/updates'].includes(url.pathname))return route.fulfill({json:{summary:summary(),jobs:[],removed:[],total_rows:0,next_cursor:null,scanned_to:'end'}});
  throw Error('Unexpected request '+url.pathname);
 });
 await page.goto('https://health.fixture/');await page.locator('#transfer-status').getByText(/Maximum speed.*uncapped/).waitFor();
 assert.match(await page.locator('#human').innerText(),/Backlog failures 28/);
 assert.equal(await page.locator('#transfer-pause').innerText(),'Pause after current transfer');
 await page.locator('#transfer-mode').selectOption('Manual');await page.locator('#transfer-manual').fill('4');await page.locator('#transfer-apply').click();
 await page.locator('#transfer-status').getByText(/Requested Manual.*Effective: Maximum speed/).waitFor();assert.equal(command.settings.manual_mbps,4);
 ack=true;await page.locator('#refresh').click();await page.locator('#transfer-status').getByText(/Effective: Manual.*4.00 Mbps/).waitFor();
 phase='Paused';resumable=true;await page.locator('#refresh').click();await page.locator('#transfer-progress').getByText(/Paused/).waitFor();assert(!/ETA|payload average/.test(await page.locator('#transfer-progress').innerText()));
 phase='Uploaded, verifying';await page.locator('#refresh').click();await page.locator('#transfer-progress').getByText(/Uploaded — verifying/).waitFor();assert(!/ETA|payload average/.test(await page.locator('#transfer-progress').innerText()));
 phase='Cloud Ready';await page.locator('#refresh').click();await page.locator('#transfer-progress').getByText(/Cloud Ready/).waitFor();
 attention={design:'Fixture PSD',diagnostic:{description:'Insufficient available memory.',recommended_action:'Close applications you are finished with, then retry the retained job.'}};
 await page.locator('#refresh').click();await page.locator('#transfer-guidance').getByText(/Recent job failure: Fixture PSD.*Close applications/).waitFor();
 attention=null;cap=1;phase='Uploading';await page.locator('#refresh').click();await page.waitForFunction(()=>document.getElementById('transfer-pause').textContent==='Pause after current transfer');
 cap=0;await page.locator('#refresh').click();await page.locator('#transfer-status').getByText(/unsupported/).waitFor();assert(await page.locator('#transfer-apply').isDisabled());
 cap=3;await page.locator('#refresh').click();await page.waitForFunction(()=>document.getElementById('transfer-pause').textContent==='Pause at chunk boundary');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));fs.mkdirSync('output/companion-phase5',{recursive:true});await page.screenshot({path:`output/companion-phase5/worker-health-${width}.png`});
 await page.close();console.log(`Phase 5 UI ${width}: cap3, Maximum preserved, requested/effective, truthful pause/ETA, verification, recent memory and old backlog, older capabilities passed`);
 }}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
