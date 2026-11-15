// Isolated browser fixtures only. All requests intercepted; no live app or data.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('components/auto_editions/bulk.html','utf8');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==','base64');
const catalogue=Array.from({length:60},(_,i)=>({product_gid:'gid://shopify/Product/'+(i+1),hash:'a'.repeat(64),title:'Artwork '+(i+1),eligible:true,reason:''}));
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const data=(cursor=0)=>({rows:catalogue.slice(cursor,cursor+10),next_cursor:cursor+10<catalogue.length?cursor+10:null,total_remaining:catalogue.length,duration_ms:10});
const report=[];
async function fixture(browser,{width=1280,clock=false,list,image,previews,body=html}={}){
 const page=await browser.newPage({viewport:{width,height:800}}),state={lists:[],images:0,active:0,maxActive:0,large:0,approvals:[],aborted:0,errors:[]};
 page.on('pageerror',e=>state.errors.push(e.message));page.on('requestfailed',r=>{if(r.url().includes('/bulk/'))state.aborted++;});
 if(clock)await page.clock.install();
 await page.route('**/*',async route=>{const url=new URL(route.request().url());
  if(url.pathname==='/')return route.fulfill({contentType:'text/html',body});
  if(url.pathname.endsWith('/previews'))return previews?previews(route,state):route.fulfill({json:{rows:[]}});
   if(url.pathname.endsWith('/list')){const request=route.request().postDataJSON();state.lists.push(request);if(list)return list(route,request,state);return route.fulfill({json:data(request.cursor||0)});}
  if(url.pathname.endsWith('/image')){if(url.searchParams.has('large'))state.large++;else state.images++;state.active++;state.maxActive=Math.max(state.maxActive,state.active);if(image)return image(route,url,state);await sleep(15);state.active--;return route.fulfill({contentType:'image/png',body:png});}
  if(url.pathname.endsWith('/approve')){const body=route.request().postDataJSON();state.approvals.push(body);return route.fulfill({status:202,json:{accepted:true,batch_id:body.request_id}});}
  if(url.pathname.endsWith('/progress')){const body=state.approvals.at(-1),items=body?.items||[];return route.fulfill({json:{found:true,active:false,counts:{Pending:0,Processing:0,Approved:items.length,Skipped:0,'Needs Attention':0,Failed:0},rows:items.map(i=>({...i,state:'Approved',current_status:'Cloud Ready',current_hash:i.hash,reason:''}))}});}
  return route.abort();
 });
 await page.goto('https://bulk-loading.local.test/');
 const start=()=>page.evaluate(ids=>postMessage({type:'sports-cave-bulk-products',product_gids:ids},location.origin),catalogue.map(r=>r.product_gid));
 return {page,state,start};
}
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 // Reproduce the old endless state with an actually pending fetch, not a guessed delay.
 if(fs.existsSync('output/bulk-loading/before-bulk.html')){
  const f=await fixture(browser,{clock:true,body:fs.readFileSync('output/bulk-loading/before-bulk.html','utf8'),list:async route=>{await sleep(1500);await route.abort().catch(()=>{});}});
  await f.start();await f.page.waitForRequest('**/bulk/list').catch(()=>{});
  await f.page.clock.fastForward(120000);assert((await f.page.locator('#message').innerText()).includes('Loading review metadata'));
  report.push({scenario:'before: stalled metadata',virtual_elapsed_ms:120000,result:'Still Loading review metadata; no timeout or Retry'});await f.page.close();
 }
 for(const width of [1280,390]){
  const f=await fixture(browser,{width,list:async(route,request)=>{await sleep(request.cursor?250:80);return route.fulfill({json:data(request.cursor)});}}),{page,state}=f;
  const began=Date.now();await f.start();await page.locator('#grid figure').first().waitFor();const firstGallery=Date.now()-began;
  assert.equal(await page.locator('#grid figure').count(),10);await page.locator('#grid input:not(:disabled)').first().waitFor();
  assert(state.images<=10,'Only current batch thumbnails are requested');assert(state.maxActive<=3);assert.equal(state.large,0);assert.equal(state.approvals.length,0);
  const firstId=await page.locator('#grid input:not(:disabled)').first().getAttribute('value');await page.locator('#grid input[value="'+firstId+'"]').check();
  await page.locator('#next').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/11'));
  assert.equal(await page.locator('#grid input:checked').count(),0,'Current batch selection only');
  await page.locator('#next').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/21'));
  assert.equal(new Set(await page.locator('#grid input').evaluateAll(nodes=>nodes.map(n=>n.value))).size,10);
  await page.locator('#previous').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/11'));
  await page.locator('#previous').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/1'));await page.locator('#grid input:not(:disabled)').first().waitFor();
  assert(await page.locator('#grid input[value="'+firstId+'"]').isChecked(),'Selection survives returning to batch');
  await page.locator('#approve').click();assert.equal(state.approvals.length,0);assert((await page.locator('#confirmation').innerText()).includes('1 designs in this batch'));
  await page.locator('#confirm').check();await page.locator('#accept').click();await page.getByText('Pending: 0 / Processing: 0 / Approved: 1 / Skipped: 0 / Needs Attention: 0 / Failed: 0',{exact:true}).waitFor();
  assert.equal(state.approvals.length,1);assert.equal(state.approvals[0].items[0].product_gid,firstId);assert.equal(state.approvals[0].items.length,1);
  assert(state.maxActive<=3);assert.equal(state.errors.length,0);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  report.push({scenario:'progressive gallery',width,first_gallery_ms:firstGallery,metadata_pages:state.lists.length,maximum_image_concurrency:state.maxActive,...await page.evaluate(()=>reviewTimings)});
  await page.close();
 }
 {
  const f=await fixture(browser,{width:390,clock:true,list:async(route,request,state)=>{if(state.lists.length===1){await sleep(1000);return route.fulfill({json:data()}).catch(()=>{});}return route.fulfill({json:data()});}}),{page,state}=f;
  await f.start();await page.waitForFunction(()=>document.getElementById('message').textContent.includes('Loading'));
  await page.clock.fastForward(10100);await page.getByText('Review metadata timed out. Retry.',{exact:true}).waitFor();
  await page.locator('#retry').evaluate(b=>{b.click();b.click();b.click();});await page.locator('#grid figure').first().waitFor();assert.equal(state.lists.length,2,'Repeated Retry clicks share one request');
  assert(state.aborted>=1);assert.equal(state.approvals.length,0);report.push({scenario:'metadata timeout/retry',deadline_ms:10000,requests:state.lists.length});await page.close();
 }
 {
  const f=await fixture(browser,{width:390,list:async(route,request,state)=>{if(state.lists.length===1){await sleep(500);return route.fulfill({json:{...data(),rows:data().rows.map(r=>({...r,title:'STALE'}))}}).catch(()=>{});}return route.fulfill({json:data()});}}),{page,state}=f;
  await f.start();await page.waitForTimeout(40);await page.locator('#reload').click();await page.locator('#grid figure').first().waitFor();await sleep(550);
  assert.equal(await page.getByText('STALE',{exact:true}).count(),0);assert.equal(state.lists.length,2);assert.equal(await page.locator('#grid figure').count(),10);
  report.push({scenario:'refresh cancellation',requests:state.lists.length,stale_cards:0});await page.close();
 }
 {
  let fail=true;const f=await fixture(browser,{list:async(route,request)=>{if(request.cursor===10&&fail){fail=false;return route.fulfill({status:503,json:{error:'Temporary read failure. Retry.'}});}return route.fulfill({json:data(request.cursor)});}}),{page,state}=f;
  await f.start();await page.locator('#grid input:not(:disabled)').first().waitFor();await page.locator('#grid input:not(:disabled)').first().check();
  const id=await page.locator('#grid input:checked').getAttribute('value');await page.locator('#next').click();await page.getByText('Temporary read failure. Retry.',{exact:true}).waitFor();
  await sleep(120);assert.equal(state.lists.length,2,'No automatic request loop after failure');await page.locator('#retry').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/11'));
  assert.equal(state.lists[2].cursor,10);assert.equal(await page.locator('#grid input:checked').count(),0);await page.locator('#previous').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/1'));assert(await page.locator('#grid input[value="'+id+'"]').isChecked());await page.close();
 }
 {
  const f=await fixture(browser,{width:390,clock:true}),{page,state}=f;await page.clock.fastForward(5100);await page.getByText('Review could not start. Retry, or close and reopen Bulk Review.',{exact:true}).waitFor();
  assert.equal(state.lists.length,0);await f.start();await page.locator('#grid figure').first().waitFor();
  await page.evaluate(()=>postMessage({type:'sports-cave-bulk-products',product_gids:Array.from({length:60},(_,i)=>'gid://shopify/Product/'+(i+1))},location.origin));assert.equal(state.lists.length,1,'Duplicate bootstrap is idempotent');await page.close();
 }
 {
  const f=await fixture(browser,{width:390}),{page,state}=f;
  await page.evaluate(()=>{window.foreignMessages=0;addEventListener('message',e=>{if(e.data?.type==='sports-cave-bulk-products'&&e.source!==window)foreignMessages++;});const frame=document.createElement('iframe');frame.srcdoc='<script>parent.postMessage({type:"sports-cave-bulk-products",product_gids:["gid://shopify/Product/1"]},"*");</script>';document.body.append(frame);});
  await page.waitForFunction(()=>window.foreignMessages===1);assert.equal(state.lists.length,0,'Unrelated same-origin frames cannot bootstrap review');
  await f.start();await page.locator('#grid figure').first().waitFor();assert.equal(state.lists.length,1);await page.close();
 }
 {
  let firstAttempt=true;
  const f=await fixture(browser,{width:390,clock:true,image:async(route,url,state)=>{
    if(url.searchParams.get('product_gid')===catalogue[0].product_gid&&firstAttempt){firstAttempt=false;await sleep(700);state.active--;return route.fulfill({contentType:'image/png',body:png}).catch(()=>{});}
    state.active--;return route.fulfill({contentType:'image/png',body:png});
  }}),{page,state}=f;
  await f.start();await page.locator('#grid figure').first().waitFor();await sleep(50);await page.clock.fastForward(15100);
  await page.clock.fastForward(1800);await page.waitForFunction(()=>!document.querySelector('#grid input').disabled);
  assert.equal(state.approvals.length,0);assert.equal(state.large,0);report.push({scenario:'thumbnail timeout',deadline_ms:10000,retry:'one automatic retry'});await page.close();
 }
 {
  const f=await fixture(browser,{list:async route=>{await sleep(500);await route.abort().catch(()=>{});}}),{page,state}=f;await f.start();await sleep(40);
  await page.evaluate(()=>postMessage({type:'sports-cave-bulk-close'},location.origin));await sleep(120);assert(state.aborted>=1);assert.equal(state.lists.length,1);assert.equal(state.errors.length,0);await page.close();
 }
 {
  let calls=0,failed=true;const attempts=new Map();const f=await fixture(browser,{clock:true,previews:route=>{calls++;for(const i of route.request().postDataJSON().items)attempts.set(i.product_gid,(attempts.get(i.product_gid)||0)+1);return failed?route.fulfill({status:503,json:{error:'Temporary preview cache outage'}}):route.fulfill({json:{rows:route.request().postDataJSON().items.map(i=>({...i,jpeg:png.toString('base64')}))}});}});
  await f.start();await f.page.locator('#grid figure').first().waitFor();await sleep(50);await f.page.clock.fastForward(1800);await f.page.locator('#grid figure').first().getByRole('button',{name:'Retry Preview'}).waitFor();assert.equal(f.state.images,0,'Cache outage must not fan out into image requests');await f.page.clock.fastForward(10000);assert([...attempts.values()].every(n=>n<=2),'Only one automatic retry per preview');failed=false;await f.page.locator('#grid figure').first().getByRole('button',{name:'Retry Preview'}).click();await f.page.locator('#grid input:not(:disabled)').first().waitFor();assert.equal(f.state.approvals.length,0);await f.page.close();
 }
 {
  const f=await fixture(browser,{clock:true,previews:route=>route.fulfill({json:{rows:route.request().postDataJSON().items.map(i=>({...i,state:'Loading',jpeg:null}))}})});
  await f.start();await f.page.locator('#grid figure').first().waitFor();await sleep(50);await f.page.evaluate(()=>{for(const r of rows)r.previewStarted=performance.now()-90001;});await f.page.clock.fastForward(3000);await f.page.locator('#grid figure').first().getByRole('button',{name:'Retry Preview'}).waitFor();assert.equal(f.state.images,0);assert.equal(await f.page.locator('#grid input:not(:disabled)').count(),0);await f.page.close();
 }
 fs.mkdirSync('output/bulk-loading',{recursive:true});fs.writeFileSync('output/bulk-loading/browser-performance.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));console.log('Progressive loading, lazy bounded images, selections, explicit approvals, stalled requests, Retry, stale cancellation, bounded cache-outage retries, pending-preview deadline and popup cleanup passed.');
 }finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
