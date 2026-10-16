// Synthetic intercepted gallery and isolated native editor; no application startup.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});const report=[];try{
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:850}});let active=0,maxActive=0,downloads=0,large=0,approvals=0,acceptedItems=[];
  const rows=Array.from({length:48},(_,n)=>({product_gid:'gid://shopify/Product/'+(n+1),hash:'a'.repeat(64),title:'Synthetic artwork '+(n+1),eligible:n<40,reason:'Needs evidence'}));
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==','base64');
  await page.route('**/*',async route=>{const u=new URL(route.request().url());
   if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/auto_editions/bulk.html','utf8')});
   if(u.pathname.endsWith('/previews'))return route.fulfill({json:{rows:[]}});
   if(u.pathname.endsWith('/list')){const cursor=route.request().postDataJSON().cursor||0;return route.fulfill({json:{rows:rows.slice(cursor,cursor+20),next_cursor:cursor+20<rows.length?cursor+20:null,metadata_queries:3,duration_ms:1}});}
   if(u.pathname.endsWith('/image')){if(u.searchParams.has('large'))large++;else downloads++;active++;maxActive=Math.max(active,maxActive);await new Promise(r=>setTimeout(r,15));active--;return route.fulfill({contentType:'image/png',body:png});}
   if(u.pathname.endsWith('/approve')){approvals++;const body=route.request().postDataJSON();assert.equal(body.confirm_visual_quality,true);assert.equal(body.items.length,40);acceptedItems=body.items;return route.fulfill({status:202,json:{accepted:true,batch_id:body.request_id}});}
   if(u.pathname.endsWith('/progress')){return route.fulfill({json:{found:true,active:false,counts:{Pending:0,Processing:0,Approved:acceptedItems.length?39:0,Skipped:acceptedItems.length?1:0,'Needs Attention':0,Failed:0},rows:acceptedItems.map((i,n)=>({...i,state:n?'Approved':'Skipped',current_status:n?'Cloud Ready':undefined,current_hash:i.hash,reason:''}))}});}
   throw Error('Unexpected request '+u.pathname);
  });
  await page.goto('https://bulk.local.test/');await page.evaluate(ids=>window.postMessage({type:'sports-cave-bulk-products',product_gids:ids},location.origin),rows.map(r=>r.product_gid));
  await page.locator('#grid figure').first().waitFor();for(;;){const previous=await page.locator('#grid figure').count();if(previous>=48)break;await page.waitForFunction(()=>document.querySelectorAll('#grid figure').length===48||!document.getElementById('more').disabled);await page.locator('#more').evaluate(n=>{n.scrollIntoView();if(!n.hidden&&!n.disabled)n.click();});await page.waitForFunction(n=>document.querySelectorAll('#grid figure').length>n,previous);}
  for(let index=0;index<48;index++)await page.locator('#grid img').nth(index).scrollIntoViewIfNeeded();await page.waitForFunction(()=>[...document.querySelectorAll('#grid img')].every(img=>img._row.previewReady));
  assert(maxActive<=3,'Bounded thumbnail requests');assert.equal(downloads,48);assert.equal(large,0);assert.equal(approvals,0);
  assert.equal(await page.locator('#grid input:disabled').count(),8);await page.locator('#grid input').first().check();assert(await page.locator('#approve').isEnabled());
  await page.locator('#grid img').first().click();await page.locator('#large[open]').waitFor();await page.locator('#close-large').click();assert.equal(large,1);
  await page.locator('#select').click();assert.equal(await page.locator('#grid input:checked').count(),40);await page.locator('#approve').click();assert.equal(approvals,0);assert(await page.locator('#accept').isDisabled());await page.locator('#confirm').check();await page.locator('#accept').click();await page.getByText('Pending: 0 / Processing: 0 / Approved: 39 / Skipped: 1 / Needs Attention: 0 / Failed: 0',{exact:true}).waitFor();assert.equal(approvals,1);assert.equal(downloads,48);assert.equal(await page.locator('#grid input:checked').count(),0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No mobile overflow');
  const metrics=await page.evaluate(()=>reviewTimings);report.push({width,products:48,maxConcurrentThumbnails:maxActive,...metrics});fs.mkdirSync('output/bulk-review',{recursive:true});await page.screenshot({path:`output/bulk-review/gallery-${width}.png`,fullPage:true});await page.close();
 }
 // Exercise the actual bundled Glide header and Streamlit fragment with synthetic rows.
 for(const width of [1440,390]){
 const page=await browser.newPage({viewport:{width,height:900}});let nativeLists=0;
 await page.route('**/auto-editions/bulk',route=>route.fulfill({contentType:'text/html',body:fs.readFileSync('components/auto_editions/bulk.html','utf8').replace('<script>','<script>window.bootstrapEvents=[];addEventListener("message",e=>bootstrapEvents.push({type:e.data?.type,parent:e.source===parent,sameOrigin:e.origin===location.origin}));')}));
 await page.route('**/bulk/list',route=>{nativeLists++;assert.equal(route.request().postDataJSON().product_gids.length,334);return route.fulfill({json:{rows:Array.from({length:20},(_,n)=>({product_gid:'gid://shopify/Product/'+(n+1),hash:'a'.repeat(64),title:'Native review '+n,eligible:true,reason:''})),next_cursor:null,duration_ms:1}});});
 await page.route('**/bulk/image?**',route=>route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==','base64')}));
 await page.goto('http://127.0.0.1:8645');await page.locator('[data-testid=stDataFrame] canvas').first().waitFor();
 if(width>800){const box=await page.locator('[data-testid=stDataFrame] canvas').first().boundingBox();await page.mouse.dblclick(box.x+420,box.y+49);const input=page.locator('.gdg-input');await input.waitFor();await input.fill('42');await input.press('Enter');await page.getByText('1 unsaved change',{exact:false}).waitFor();}
 const scroll=page.locator('.dvn-scroller').first();await scroll.evaluate(n=>{n.scrollLeft=10000;n.scrollTop=500;});
 const menu=page.getByRole('button',{name:'Auto Editions menu: Bulk Review and Sort by'});await menu.waitFor();
 const before=await page.getByText('fixture-main-runs:',{exact:false}).innerText(),position=await scroll.evaluate(n=>({left:n.scrollLeft,top:n.scrollTop}));
 await page.evaluate(()=>{
  const frame=[...document.querySelectorAll('iframe')].find(f=>f.src.includes('edition_auto_live'));
  const rows=(window.SportsCaveEditionStatusState.rows||[]).map(r=>({...r,review_operation:{label:'Approving'+String.fromCharCode(8230)}}));
  frame.contentWindow.postMessage({type:'streamlit:render',args:{product_gids:rows.map(r=>r.product_gid),rows}},location.origin);
 });
 await page.locator('.sc-review-spinner').first().waitFor();
 assert.equal(await page.getByText('fixture-main-runs:',{exact:false}).innerText(),before,'Spinner does not rerun app');
 await menu.click();for(const label of ['Failed First','Not Connected First','Queued First','Needs Review First','Synced / Cloud Ready First','Default Order'])assert(await page.getByRole('menuitem',{name:label,exact:true}).isVisible());
 await page.getByRole('menuitem',{name:'Needs Review First',exact:true}).click();await page.waitForFunction(()=>window.SportsCaveEditionStatusState?.nonce>0);await page.waitForTimeout(1000);
 assert.equal(await page.getByText('fixture-main-runs:',{exact:false}).innerText(),before,'Sorting stays in fragment');assert.deepEqual(await scroll.evaluate(n=>({left:n.scrollLeft,top:n.scrollTop})),position,'Scroll preserved');
 if(width>800)await page.getByText('1 unsaved change',{exact:false}).waitFor();
 await menu.click();await page.getByRole('button',{name:'Bulk Review',exact:true}).click();const review=page.frameLocator('iframe[title="Bulk artwork review"]');try{await review.locator('#grid figure').first().waitFor({timeout:7000});}catch(error){console.log(JSON.stringify({nativeLists,body:await review.locator('body').innerText(),events:await review.locator('body').evaluate(()=>window.bootstrapEvents)}));throw error;}assert.equal(await review.locator('#grid figure').count(),20);assert.equal(nativeLists,1,'Ready/load handshake starts one request');await page.getByRole('button',{name:'Close Bulk Review',exact:true}).click();
 assert.equal(await page.getByText('fixture-main-runs:',{exact:false}).innerText(),before);
 await page.close();}
 fs.writeFileSync('output/bulk-review/browser-performance.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));console.log('Bulk gallery desktop/mobile, bounded concurrency, single confirmation, result counts and native header fragment passed.');
 }finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
