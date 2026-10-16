// Actual Streamlit native popup + isolated durable service fixture. No live app, data or credentials.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('components/auto_editions/bulk.html','utf8');
const png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==';
const products=Array.from({length:60},(_,i)=>({product_gid:'gid://shopify/Product/'+(i+1),hash:'a'.repeat(64),title:'Artwork '+(i+1),eligible:true,reason:''}));
const counts=rows=>Object.fromEntries(['Pending','Processing','Approved','Skipped','Needs Attention','Failed'].map(k=>[k,rows.filter(r=>r.state===k).length]));
const sleep=ms=>new Promise(r=>setTimeout(r,ms)),report=[];
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 for(const width of [1440,390])for(const choice of ['selected','all']){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),jobs=new Map(),batches=new Map();let submissions=[],batchReads=0,individualReads=0,failSubmission=false;
  await context.request.post('http://127.0.0.1:8645/fixture-stage',{data:{stage:'Queued',review_jobs:{}}});
  await page.route('**/auto-editions/bulk',route=>route.fulfill({contentType:'text/html',body:html}));
  await page.route('**/bulk/list',route=>{
   const body=route.request().postDataJSON(),ids=new Set(body.product_gids),available=products.filter(r=>ids.has(r.product_gid)&&!['Pending','Processing','Approved'].includes(jobs.get(r.product_gid)?.state));
   const rows=available.slice(body.cursor,body.cursor+20).map(r=>({...r,reason:jobs.get(r.product_gid)?.state==='Failed'?'Previous approval failed. Retry available.':''}));
   return route.fulfill({json:{rows,next_cursor:body.cursor+20<available.length?body.cursor+20:null}});
  });
  await page.route('**/bulk/previews',async route=>{batchReads++;await sleep(80);const items=route.request().postDataJSON().items;assert(items.length<=8);return route.fulfill({json:{rows:items.map(r=>({...r,jpeg:png}))}});});
  await page.route('**/bulk/image?**',route=>{individualReads++;return route.fulfill({contentType:'image/png',body:Buffer.from(png,'base64')});});
  await page.route('**/bulk/approve',async route=>{
   const body=route.request().postDataJSON();submissions.push(body);assert.equal(body.confirm_visual_quality,true);
   if(failSubmission)return route.fulfill({status:503,json:{error:'Temporary acceptance failure'}});
   if(!batches.has(body.request_id)){
    batches.set(body.request_id,body.items);for(const item of body.items)jobs.set(item.product_gid,{...item,job_id:item.product_gid,state:'Pending',reason:''});
   }
   const fixture=Object.fromEntries([...jobs].map(([pid,row])=>[pid,{hash:row.hash,label:'Pending Approval'}]));
   await context.request.post('http://127.0.0.1:8645/fixture-stage',{data:{stage:'Queued',review_jobs:fixture}});
   await sleep(80);return route.fulfill({status:202,json:{accepted:true,batch_id:body.request_id}});
  });
  await page.route('**/bulk/progress',route=>{const body=route.request().postDataJSON(),items=body.batch_id?batches.get(body.batch_id):null;
   const rows=[...jobs.values()].filter(r=>!items||items.some(i=>i.product_gid===r.product_gid)).map(r=>({...r,current_status:r.state==='Approved'?'Cloud Ready':undefined,current_hash:r.hash}));
   return route.fulfill({json:{found:!body.batch_id||batches.has(body.batch_id),rows,counts:counts(rows),active:rows.some(r=>['Pending','Processing'].includes(r.state))}});
  });
  await page.goto('http://127.0.0.1:8645');await page.locator('[data-testid=stDataFrame] canvas').first().waitFor();
  if(width>800){const bounds=await page.locator('[data-testid=stDataFrame] canvas').first().boundingBox();await page.mouse.dblclick(bounds.x+420,bounds.y+49);const edit=page.locator('.gdg-input');await edit.fill('42');await edit.press('Enter');await page.getByText('1 unsaved change',{exact:false}).waitFor();}
  const scroll=page.locator('.dvn-scroller').first();await scroll.evaluate(n=>{n.scrollLeft=10000;n.scrollTop=0;});
  const before=await page.getByText('fixture-main-runs:',{exact:false}).innerText(),position=await scroll.evaluate(n=>({top:n.scrollTop,left:n.scrollLeft}));
  const open=async()=>{await page.getByRole('button',{name:'Auto Editions menu: Bulk Review and Sort by'}).click();await page.getByRole('button',{name:'Bulk Review',exact:true}).click();};
  await open();let review=page.frameLocator('iframe[title="Bulk artwork review"]');await review.locator('#grid figure').first().waitFor();
  // All means all loaded metadata. Add two pages without scrolling past every image.
  for(let target=40;target<=60;target+=20){await review.locator('#more').evaluate(b=>b.click());await review.locator('#grid figure').nth(target-1).waitFor();}
  await review.locator('#grid input:not(:disabled)').first().waitFor();
  if(choice==='all'){
   assert((await review.locator('#grid input:not(:disabled)').count())<60,'Some loaded designs are offscreen and have not loaded thumbnails');
   await review.locator('#all').click();await review.locator('#proof[open]').waitFor();
   assert((await review.locator('#confirmation').innerText()).includes('60 loaded designs'),'Approve All must include offscreen loaded designs');
  }else{
   await review.locator('#grid input:not(:disabled)').nth(0).check();await review.locator('#grid input:not(:disabled)').nth(1).check();await review.locator('#approve').click();
  }
  // Unrelated same-origin messages cannot close the popup.
  await page.evaluate(()=>postMessage({type:'sports-cave-bulk-accepted',batch_id:'forged'},location.origin));assert(await page.getByRole('dialog',{name:'Bulk Review',exact:true}).isVisible());
  assert(await review.locator('#accept').isDisabled());await review.locator('#confirm').check();const started=Date.now();
  await review.locator('#accept').evaluate(b=>{b.click();b.click();});await page.getByRole('dialog',{name:'Bulk Review',exact:true}).waitFor({state:'detached'});
  assert.equal(submissions.length,1,'Double-click is one submission');assert.equal(jobs.size,choice==='all'?60:2);
  const selected=[...jobs.keys()];await page.waitForFunction(pid=>window.SportsCaveEditionStatusState?.rows.some(r=>r.product_gid===pid&&r.review_operation?.label==='Pending Approval'),selected[0]);
  assert.equal(await page.getByText('fixture-main-runs:',{exact:false}).innerText(),before,'Only the fragment updates');
  assert.deepEqual(await scroll.evaluate(n=>({top:n.scrollTop,left:n.scrollLeft})),position,'Main scrolling is preserved');
  if(width>800)await page.getByText('1 unsaved change',{exact:false}).waitFor();
  report.push({width,choice,accepted:jobs.size,close_after_confirm_ms:Date.now()-started,cache_batches:batchReads,individual_preview_requests:individualReads});
  await open();review=page.frameLocator('iframe[title="Bulk artwork review"]');
  if(choice==='all')await review.locator('#message').filter({hasText:'No designs need review'}).waitFor();else await review.locator('#grid figure').first().waitFor();
  for(const pid of selected)assert.equal(await review.locator('input[value="'+pid+'"]').count(),0,'Persisted Pending jobs excluded on reopen');
  // A partial background failure must reappear automatically; a committed success must not.
  for(const job of jobs.values())job.state='Approved';const failed=jobs.get(selected.at(-1));failed.state='Failed';failed.reason='Temporary provider failure. Retry available.';
  await review.locator('body').evaluate(()=>trackApprovals());await review.locator('input[value="'+failed.product_gid+'"]').waitFor();
  for(const pid of selected.slice(0,-1))assert.equal(await review.locator('input[value="'+pid+'"]').count(),0);
  assert((await review.locator('#progress').innerText()).includes('Failed: 1'));
  // A failed acceptance never closes or removes the retry card.
  await review.locator('input[value="'+failed.product_gid+'"]').check();await review.locator('#approve').click();await review.locator('#confirm').check();failSubmission=true;await review.locator('#accept').click();
  await review.locator('#retry-approval').waitFor();assert(await page.getByRole('dialog',{name:'Bulk Review',exact:true}).isVisible());assert(await review.locator('input[value="'+failed.product_gid+'"]').count());
  await context.close();
 }
 {
  const page=await browser.newPage({viewport:{width:390,height:800}});let submitted=null;
  await page.route('**/*',route=>{const path=new URL(route.request().url()).pathname;
   if(path==='/')return route.fulfill({contentType:'text/html',body:html});
   if(path.endsWith('/list'))return route.fulfill({json:{rows:products.slice(0,20),next_cursor:null}});
   if(path.endsWith('/previews'))return route.fulfill({json:{rows:route.request().postDataJSON().items.map(i=>({...i,jpeg:i.product_gid===products[19].product_gid?null:png}))}});
   if(path.endsWith('/image'))return route.fulfill({status:503,body:'Preview temporarily unavailable'});
   if(path.endsWith('/approve')){submitted=route.request().postDataJSON();return route.fulfill({status:503,json:{error:'Not accepted'}});}
   if(path.endsWith('/progress'))return route.fulfill({json:{found:false,rows:[],counts:counts([]),active:false}});
   return route.abort();
  });
  await page.goto('https://all-preview-retry.local.test/');await page.evaluate(ids=>postMessage({type:'sports-cave-bulk-products',product_gids:ids},location.origin),products.slice(0,20).map(r=>r.product_gid));
  await page.locator('#grid figure').first().waitFor();await page.locator('#all').click();await page.locator('#proof[open]').waitFor();
  const text=await page.locator('#confirmation').innerText();assert(text.includes('19 loaded designs')&&text.includes('1 unavailable previews excluded'));
  await page.locator('#confirm').check();await page.locator('#accept').click();await page.locator('#retry-approval').waitFor();
  assert.equal(submitted.items.length,19);assert(!submitted.items.some(i=>i.product_gid===products[19].product_gid));assert.equal(await page.locator('#grid figure').count(),20,'Failed acceptance must retain every card');
  await page.close();
 }
 fs.mkdirSync('output/bulk-handoff',{recursive:true});fs.writeFileSync('output/bulk-handoff/browser-native.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));console.log('Selected/all loaded, durable close, signed main status, immediate reopen, failed restore, duplicates and native edit/scroll preservation passed.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
