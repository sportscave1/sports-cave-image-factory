// Offline Worker Health provenance fixture; no app startup or provider traffic.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
for(const width of [1280,390]){
 const page=await browser.newPage({viewport:{width,height:800}});await page.clock.install();
 const jobs=['Auto Approved','Needs Review','Failed'].map((status,i)=>({id:'gid://shopify/Product/'+(1000+i),design:'Synthetic artwork '+i,priority:1,stage:'Review',status,category:['Completed','Needs Review','Failed'][i],approval_status:i===1?'Auto Approved':status,attempts:1,checkpoint:'Automatic visual assessment',reason:i===1?'Mandatory supplier certification is pending.':'Exact evidence status recorded.',last_activity:'Fixture'}));
 await page.route('**/*',route=>{const u=new URL(route.request().url());
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/worker_health/index.html','utf8')});
  if(u.pathname==='/api/worker-health')return route.fulfill({json:{overall:'Idle',control:{paused:false},counts:{completed:3,eligible:3,remaining:0,review:1,repair:0,failed:1},progress:{completed:3,total:3},current:null,eta_seconds:0,eta_samples:0,eta_label:'No runnable backlog',last_completed:null,updated_at:'Fixture',revision:'local',health:[],warnings:[],filters:{All:3},total_rows:3,jobs}});
  if(u.pathname==='/api/worker-health/diagnostics')return route.fulfill({json:{rows:[],next_cursor:null}});
  throw Error('Unexpected network request '+u.pathname);
 });
 await page.goto('https://visual.local.test/');await page.waitForFunction(()=>data!==null);
 assert.equal(await page.locator('#jobs tr[data-id]').count(),3);
 assert.equal(await page.locator('#jobs tr[data-id]').first().locator('td').nth(3).textContent(),'Auto Approved');
 await page.locator('#jobs tr[data-id]').nth(1).click();
 assert((await page.locator('tr.details').innerText()).includes('Visual: Auto Approved · Mandatory supplier certification is pending.'));
 await page.evaluate(()=>render(data));assert.equal(await page.locator('tr.details').count(),1);
 assert.equal(await page.locator('h1').textContent(),'Worker Health');
 console.log('Automatic visual provenance and supplier exception passed '+width);await page.close();
}
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
