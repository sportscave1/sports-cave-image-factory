// Actual native Streamlit grid; synthetic HTTP state only. Backend validation is
// separately exercised with real immutable assets and disposable SQL in pytest.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const base='http://127.0.0.1:8645',html=fs.readFileSync('components/auto_editions/bulk.html','utf8');
const png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==';
const products=Array.from({length:36},(_,n)=>({product_gid:'gid://shopify/Product/'+(n+1),hash:'a'.repeat(64),title:'Review '+(n+1),eligible:true,reason:''}));
const counts=rows=>Object.fromEntries(['Pending','Processing','Approved','Skipped','Needs Attention','Failed'].map(k=>[k,rows.filter(r=>r.state===k).length]));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const context=await browser.newContext({viewport:{width:1440,height:900}}),page=await context.newPage();
 const jobs=new Map(),batches=new Map(),submissions=[],errors=[];let statusActive=0,maxStatusActive=0,statusCalls=0,previewCalls=0,previewBytes=0,expired=true;
 page.on('pageerror',e=>errors.push(e.message));
 await context.request.post(base+'/fixture-stage',{data:{stage:'Queued',review_jobs:Object.fromEntries(products.map(r=>[r.product_gid,{hash:r.hash,label:'Needs Review'}]))}});
 await page.route('**/api/auto-editions/status',async route=>{statusCalls++;statusActive++;maxStatusActive=Math.max(maxStatusActive,statusActive);try{await sleep(80);const response=await route.fetch();await route.fulfill({response});}finally{statusActive--;}});
 await page.route('**/auto-editions/bulk',r=>r.fulfill({contentType:'text/html',body:html}));
 await page.route('**/bulk/list',r=>{const b=r.request().postDataJSON(),available=products.filter(p=>b.product_gids.includes(p.product_gid)&&!['Pending','Processing','Approved'].includes(jobs.get(p.product_gid)?.state));return r.fulfill({json:{rows:available.slice(b.cursor,b.cursor+20),next_cursor:b.cursor+20<available.length?b.cursor+20:null}});});
 await page.route('**/bulk/previews',async r=>{previewCalls++;const items=r.request().postDataJSON().items;assert(items.length<=8);await sleep(20);const rows=items.map(i=>({...i,jpeg:expired&&i.product_gid===products[0].product_gid?null:png,...(expired&&i.product_gid===products[0].product_gid?{state:'Unavailable',error:'Preview access expired. Retry Preview.'}:{})}));previewBytes+=rows.filter(r=>r.jpeg).length*Buffer.from(png,'base64').length;return r.fulfill({json:{rows}});});
 await page.route('**/bulk/image?**',()=>{throw Error('Warm previews should not fall through to individual requests');});
 await page.route('**/bulk/approve',async route=>{
  const b=route.request().postDataJSON();submissions.push(b);
  if(!batches.has(b.request_id)){
   batches.set(b.request_id,b.items);for(const i of b.items)jobs.set(i.product_gid,{...i,job_id:i.product_gid,state:submissions.length===1&&i.product_gid===products[35].product_gid?'Failed':'Pending',reason:i.product_gid===products[35].product_gid?'Temporary validation failure. Retry available.':''});
  }
  const fixture=Object.fromEntries([...jobs].map(([pid,j])=>[pid,{hash:j.hash,label:j.state==='Failed'?'Approval Failed':'Approving…'}]));
  await context.request.post(base+'/fixture-stage',{data:{stage:'Queued',review_jobs:fixture}});
  const rows=b.items.map(i=>jobs.get(i.product_gid));await sleep(40);await route.fulfill({status:202,json:{batch_id:b.request_id,accepted:true,rows,counts:counts(rows),active:true}});
 });
 await page.route('**/bulk/progress',r=>{const b=r.request().postDataJSON(),items=b.batch_id?batches.get(b.batch_id):null;
  const rows=[...jobs.values()].filter(j=>!items||items.some(i=>i.product_gid===j.product_gid)).map(j=>({...j,current_status:j.state==='Approved'?'Cloud Ready':undefined,current_hash:j.hash}));
  return r.fulfill({json:{found:!b.batch_id||batches.has(b.batch_id),rows,counts:counts(rows),active:rows.some(j=>['Pending','Processing'].includes(j.state))}});
 });
 await page.goto(base);await page.locator('[data-testid=stDataFrame] canvas').first().waitFor();
 const scroll=page.locator('.dvn-scroller').first();await scroll.evaluate(n=>{n.scrollLeft=10000;n.scrollTop=0;});
 const position=await scroll.evaluate(n=>({top:n.scrollTop,left:n.scrollLeft})),runs=await page.getByText('fixture-main-runs:',{exact:false}).innerText();
 const open=async()=>{await page.getByRole('button',{name:'Auto Editions menu: Bulk Review and Sort by'}).click();await page.getByRole('button',{name:'Bulk Review',exact:true}).click();};
 const start=Date.now();await open();const review=page.frameLocator('iframe[title="Bulk artwork review"]');await review.locator('#grid input:not(:disabled)').first().waitFor();const firstVisible=Date.now()-start;
 await review.locator('figure').first().getByRole('button',{name:'Retry Preview'}).waitFor();expired=false;await review.locator('figure').first().getByRole('button',{name:'Retry Preview'}).click();await review.locator('input[value="'+products[0].product_gid+'"]').waitFor({state:'visible'});await review.locator('input[value="'+products[0].product_gid+'"]').check();
 if(await review.locator('#grid figure').count()<36)await review.locator('#more').evaluate(n=>n.click());await review.locator('#grid figure').nth(35).waitFor();
 for(let i=0;i<36;i++)await review.locator('#grid figure').nth(i).scrollIntoViewIfNeeded();
 await review.locator('#grid input:not(:disabled)').nth(35).waitFor();assert(await review.locator('input[value="'+products[0].product_gid+'"]').isChecked(),'Loading/scrolling preserves selection');
 await review.locator('#select').click();await review.locator('#approve').click();await review.locator('#confirm').check();const submitted=Date.now();await review.locator('#accept').evaluate(n=>{n.click();n.click();});
 await review.locator('#progress').filter({hasText:'Pending: 35 / Processing: 0 / Approved: 0 / Skipped: 0 / Needs Attention: 0 / Failed: 1'}).waitFor();
 await page.waitForFunction(ids=>ids.slice(0,35).every(pid=>window.SportsCaveEditionStatusState.rows.find(r=>r.product_gid===pid)?.review_operation?.label==='Approving…'),products.map(r=>r.product_gid));const allApproving=Date.now()-submitted;
 assert.equal(submissions.length,1);assert.equal(submissions[0].items.length,36);assert.equal(await review.locator('small.approving').count(),35);assert.equal(await review.locator('#grid input:checked').count(),0);
 assert((await review.locator('#grid figure').nth(35).innerText()).includes('Temporary validation failure'));assert.equal(await review.locator('#grid figure').nth(35).locator('small.approving').count(),0);
 assert(await page.getByRole('dialog',{name:'Bulk Review',exact:true}).isVisible(),'Partial failure keeps its result visible');
 const polls=statusCalls;await sleep(3300);assert(statusCalls>polls,'Main batch reconciliation continues with modal open');assert.equal(maxStatusActive,1,'No overlapping status polls');
 assert.equal(await page.getByText('fixture-main-runs:',{exact:false}).innerText(),runs);assert.deepEqual(await scroll.evaluate(n=>({top:n.scrollTop,left:n.scrollLeft})),position);
 for(const [pid,j] of jobs)if(j.state!=='Failed')j.state='Approved';
 await context.request.post(base+'/fixture-stage',{data:{stage:'Cloud Ready',review_jobs:{[products[35].product_gid]:{hash:'a'.repeat(64),label:'Approval Failed'}}}});
 await review.locator('#progress').filter({hasText:'Approved: 35 / Skipped: 0 / Needs Attention: 0 / Failed: 1'}).waitFor();await review.locator('#grid figure').waitFor();assert.equal(await review.locator('#grid figure').count(),1,'Only failed card remains');
 await review.locator('#grid input').check();await review.locator('#approve').click();await review.locator('#confirm').check();await review.locator('#accept').click();await page.getByRole('dialog',{name:'Bulk Review',exact:true}).waitFor({state:'detached'});
 assert.equal(submissions.length,2);assert.equal(submissions[1].items.length,1);assert.equal(submissions[1].items[0].product_gid,products[35].product_gid);
 await open();await review.locator('#message').filter({hasText:'No designs need review'}).waitFor();assert.equal(await review.locator('#grid figure').count(),0,'Accepted products stay excluded on reopen');
 assert.deepEqual(errors,[]);
 const report={scope:'Native desktop grid; synthetic network receipts; actual backend validation tested separately',selected:36,accepted:35,failed:1,all_accepted_approving_ms:allApproving,first_visible_ms:firstVisible,preview_batch_requests:previewCalls,thumbnail_bytes:previewBytes,individual_image_requests:0,maximum_status_concurrency:maxStatusActive,main_page_reruns:0};
 fs.mkdirSync('output/bulk-reliability',{recursive:true});fs.writeFileSync('output/bulk-reliability/native-batch.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));await page.unrouteAll({behavior:'ignoreErrors'});await context.close();
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
