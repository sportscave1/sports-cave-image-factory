// Real loopback HTTP and disposable SQL; no live worker, data, or provider calls.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const url=process.env.WORKER_QUEUE_FIXTURE,context=await browser.newContext({viewport:{width:1440,height:900}}),page=await context.newPage();
 const errors=[],requests=[],active=new Map();let peak=0;page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{const original=window.fetch.bind(window);window.pollProbe={active:0,peak:0};window.fetch=async(...args)=>{const monitored=/\/api\/worker-health\/(jobs|updates)/.test(String(args[0]));if(monitored){pollProbe.active++;pollProbe.peak=Math.max(pollProbe.peak,pollProbe.active);}try{const response=await original(...args);if(monitored)await response.clone().arrayBuffer();return response;}finally{if(monitored)pollProbe.active--;}};});
 page.on('request',r=>{const path=new URL(r.url()).pathname;requests.push(path);if(['/api/worker-health/jobs','/api/worker-health/updates'].includes(path)){active.set(r,true);peak=Math.max(peak,active.size);}});
 const done=r=>active.delete(r);page.on('requestfinished',done);page.on('requestfailed',done);
 const transition=stage=>context.request.post(url+'/fixture/transition',{data:{stage}});
 const start=Date.now();await page.goto(url+'/worker-health');await page.locator('#jobs tr[data-id]').first().waitFor();const firstList=Date.now()-start;
 assert.equal(await page.getByRole('button',{name:'Previous',exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'Next',exact:true}).count(),0);
 assert.equal(requests.filter(p=>p.includes('/details')||p.includes('/diagnostics')).length,0,'Details/logs are lazy');
 for(let n=0;n<12&&await page.locator('#jobs tr[data-id]').count()<285;n++){await page.locator('#jobs-pane').evaluate(el=>el.scrollTop=el.scrollHeight);await page.waitForTimeout(180);if(await page.locator('#load-more').isVisible())await page.locator('#load-more').click();}
 await page.waitForFunction(()=>document.querySelectorAll('#jobs tr[data-id]').length===285);
 assert.equal(await page.locator('#queue-count').innerText(),'285 / 285 loaded');assert.equal(new Set(await page.locator('#jobs tr[data-id]').evaluateAll(rows=>rows.map(r=>r.dataset.id))).size,285);
 const row=page.locator('#jobs tr[data-id]').first(),pid=await row.getAttribute('data-id');await row.scrollIntoViewIfNeeded();const handle=await row.elementHandle();
 await row.getByRole('button',{name:'Details',exact:true}).click();await page.locator('tr.details summary').click();await page.locator('tr.details .technical').filter({hasText:'Download interrupted'}).waitFor();
 const beforeScroll=await page.locator('#jobs-pane').evaluate(n=>n.scrollTop),submitted=Date.now();await row.getByRole('button',{name:'Retry',exact:true}).evaluate(n=>{n.click();n.click();});
 await row.locator('td').nth(3).filter({hasText:'Pending'}).waitFor();const ack=Date.now()-submitted;await row.locator('.wh-spinner').waitFor();assert.equal(requests.filter(p=>p==='/api/worker-health/enqueue').length,1);assert(await handle.evaluate(n=>n.isConnected));
 assert.equal(await page.locator('#jobs-pane').evaluate(n=>n.scrollTop),beforeScroll);
 await page.reload();await page.locator('tr[data-id="'+pid+'"] td').nth(3).filter({hasText:'Pending'}).waitFor();
 await transition('claim');await page.locator('tr[data-id="'+pid+'"] td').nth(3).filter({hasText:'Preparing'}).waitFor({timeout:12000});
 await transition('Photoshop');await page.locator('tr[data-id="'+pid+'"] td').nth(2).filter({hasText:'Photoshop'}).waitFor({timeout:12000});
 await transition('fail');const current=page.locator('tr[data-id="'+pid+'"]');await current.locator('td').nth(3).filter({hasText:'Needs Repair'}).waitFor({timeout:12000});
 await current.getByRole('button',{name:'Retry',exact:true}).click();await page.locator('#retry-dialog').waitFor();assert(await page.locator('#retry-confirm').isDisabled());await page.locator('#retry-corrected').check();await page.locator('#retry-confirm').click();await current.locator('td').nth(3).filter({hasText:'Pending'}).waitFor();
 await transition('claim');await transition('complete');await current.locator('td').nth(3).filter({hasText:'Needs Review'}).waitFor({timeout:12000});assert.equal(await current.locator('button.retry-job').count(),1);assert(await current.locator('button.retry-job').isHidden());assert.equal(await current.locator('.wh-spinner').count(),0);
 // The source/geometry/ICC proof package is committed, but no visual approval is manufactured.
 await page.locator('#logs-panel summary').first().click();await page.locator('#design-search').fill('10001');await page.locator('#design-find').click();await page.waitForFunction(()=>document.querySelector('#design-results').options.length>0);await page.locator('#design-results').selectOption('gid://shopify/Product/10001');await page.locator('#design-queue').click();await page.locator('#design-message').filter({hasText:'Accepted:'}).waitFor();
 const position=await page.locator('#jobs-pane').evaluate(n=>n.scrollTop);await transition('fail-list');await page.locator('#filter').selectOption('Failed');await page.locator('#list-retry').waitFor();await page.locator('#list-retry').click();await page.locator('#jobs tr[data-id]').first().waitFor();
 await page.evaluate(()=>{document.dispatchEvent(new Event('visibilitychange'));});await page.waitForTimeout(300);peak=await page.evaluate(()=>pollProbe.peak);assert(peak<=1,'List and update requests do not overlap');assert.deepEqual(errors,[]);
 fs.mkdirSync('output/worker-health-queue',{recursive:true});await page.screenshot({path:'output/worker-health-queue/desktop.png'});
 await page.setViewportSize({width:390,height:800});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No mobile page overflow');
 const report={scope:'Actual HTTP endpoints, real disposable SQL and synthetic verified PNG package; no Photoshop/live provider',jobs:285,initial_list_ms:firstList,retry_ack_to_pending_ms:ack,duplicate_click_submissions:1,peak_list_requests:peak,all_rows_accessible:true,automatic_stage_failure_completion:true};
 fs.mkdirSync('output/worker-health-queue',{recursive:true});fs.writeFileSync('output/worker-health-queue/browser-performance.json',JSON.stringify(report,null,2));await page.screenshot({path:'output/worker-health-queue/desktop-mobile.png'});console.log(JSON.stringify(report));await context.close();
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
