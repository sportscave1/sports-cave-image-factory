const {packet}=require('./worker_health_protocol_fixture.cjs');
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await browser.newPage({viewport:{width:390,height:800}});await page.clock.install();
 let reads=0,hold=false,pending=[],paused=false,holdLog=false,releaseLog;const filters=[];
 const job={id:'gid://shopify/Product/1800',design:'Synthetic artwork',priority:1,stage:'Queued',status:'Queued',category:'Queued',attempts:0,checkpoint:'Mapped',actions:[]};
 const value=()=>({overall:paused?'Paused':'Idle',control:{paused},counts:{completed:0,eligible:334,remaining:334,review:0,repair:0,failed:0},progress:{completed:0,total:334},current:null,eta_seconds:null,eta_label:'Calculating',eta_samples:0,last_completed:null,updated_at:'Fixture',revision:'b177b3ea',health:[],warnings:[],filters:{All:334,Active:0,Queued:334,Failed:0,'Needs Review':0,Completed:0},total_rows:334,jobs:[job]});
 await page.route('**/*',async route=>{const u=new URL(route.request().url());
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/worker_health/index.html','utf8')});
  if(['/api/worker-health/jobs','/api/worker-health/updates'].includes(u.pathname)){
   reads++;filters.push(u.searchParams.get('filter')||route.request().postDataJSON()?.filter);const snapshot=value();
   if(hold)await new Promise(resolve=>pending.push(resolve));return route.fulfill({json:packet(snapshot,route,u)});
  }
  if(u.pathname==='/api/worker-health/control'){paused=route.request().postDataJSON().paused;return route.fulfill({json:{state:paused?'Paused':'Resumed'}});}
  if(u.pathname==='/api/worker-health/diagnostics'){
   if(holdLog&&!u.searchParams.get('search')){await new Promise(resolve=>releaseLog=resolve);try{await route.fulfill({json:{rows:[],next_cursor:null}});}catch{}return;}
   return route.fulfill({json:{rows:[{timestamp:'Fixture',component:'Photoshop',design:'Synthetic',description:'Current ICC result',trace:'AE-fixture',code:'ICC_MISMATCH',stage:'Preparing',recommended_action:'Review'}],next_cursor:null}});
  }
  throw Error('Unexpected request '+u.pathname);
 });
 await page.goto('https://v18-safe.local.test/');await page.waitForFunction(()=>data!==null&&!loading);
 // Slow automatic polls must coalesce rather than queue another refresh.
 hold=true;await page.locator('#refresh').click();await page.waitForFunction(()=>loading);const heldReads=reads;
 await page.clock.runFor(11000);assert.equal(reads,heldReads);
 hold=false;pending.splice(0).forEach(resolve=>resolve());await page.waitForFunction(()=>!loading);assert.equal(reads,heldReads);
 // A deliberate filter change still gets one follow-up snapshot.
 hold=true;await page.locator('#refresh').click();await page.waitForFunction(()=>loading);await page.locator('#filter').selectOption('Queued');
 hold=false;pending.splice(0).forEach(resolve=>resolve());await page.waitForFunction(()=>!loading);assert.equal(filters.at(-1),'Queued');
 // An old read must not undo the result of a Pause command.
 hold=true;await page.locator('#refresh').click();await page.waitForFunction(()=>loading);await page.locator('#pause').click();
 hold=false;pending.splice(0).forEach(resolve=>resolve());await page.waitForFunction(()=>!loading&&data.control.paused);assert.equal(await page.locator('#overall').innerText(),'Paused');assert(await page.locator('#resume').isEnabled());
 // A superseded slow diagnostics request cannot replace a newer search result.
 holdLog=true;await page.locator('#logs-panel summary').click();await page.waitForFunction(()=>logsController!==null);
 await page.locator('#log-search').fill('ICC');await page.locator('#log-refresh').click();await page.getByText('Fixture · Photoshop · Synthetic · Current ICC result',{exact:true}).waitFor();
 releaseLog();await page.waitForTimeout(20);assert((await page.locator('#log-list').innerText()).includes('Current ICC result'));
 await page.close();console.log('V18 UI: coalesced slow polling, intentional filter refresh, Pause/read race and superseded diagnostics passed.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
