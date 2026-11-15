// Durable service fixture survives popup/page lifetime; no real provider or application data.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('components/auto_editions/bulk.html','utf8');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==','base64');
const ids=Array.from({length:35},(_,n)=>'gid://shopify/Product/'+(n+1));
const products=ids.map((product_gid,n)=>({product_gid,hash:'a'.repeat(64),title:'Prepared artwork '+n,eligible:true,reason:''}));
const report=[];
async function fixture(context,state){
 const page=await context.newPage();await page.clock.install();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const path=new URL(route.request().url()).pathname,body=path.endsWith('/image')?{}:route.request().postDataJSON();
  if(path==='/')return route.fulfill({contentType:'text/html',body:html.replace('<script>','<script>window.handoffs=[];addEventListener("message",e=>{if(e.data?.type==="sports-cave-bulk-accepted")handoffs.push(e.data.batch_id)});')});
  if(path.endsWith('/previews'))return route.fulfill({json:{rows:[]}});
   if(path.endsWith('/list')){const cursor=body.cursor;const pending=new Set((state.items||[]).filter((r,n)=>!state.complete||n!==1).map(r=>r.product_gid)),available=products.filter(r=>!pending.has(r.product_gid)&&body.product_gids.includes(r.product_gid));return route.fulfill({json:{rows:available.slice(cursor,cursor+10),next_cursor:cursor+10<available.length?cursor+10:null}});}
  if(path.endsWith('/image')){if(state.previewFailure){state.previewFailure=false;return route.fulfill({status:503,body:'Temporary transfer error'});}return route.fulfill({contentType:'image/png',body:png});}
  if(path.endsWith('/approve')){
   state.submissions.push(body);assert.equal(body.confirm_visual_quality,true);
   if(state.noCommitFirst){state.noCommitFirst=false;return route.abort();}
   if(!state.key){state.key=body.request_id;state.items=body.items;}
   assert.equal(body.request_id,state.key,'No new idempotency key on uncertain acknowledgement');
   if(state.dropAck){state.dropAck=false;return route.abort();}
   return route.fulfill({status:202,json:{accepted:true,batch_id:state.key}});
  }
  if(path.endsWith('/progress')){
   state.polls++;const rows=(state.items||[]).map((i,n)=>({...i,state:state.complete?(n===1?'Needs Attention':'Approved'):state.processing?'Processing':'Pending',current_status:state.complete&&n!==1?'Cloud Ready':undefined,current_hash:i.hash,reason:n===1?'Missing current proof. Use Review / Repair.':''}));
   const counts=Object.fromEntries(['Pending','Processing','Approved','Skipped','Needs Attention','Failed'].map(s=>[s,rows.filter(r=>r.state===s).length]));
   return route.fulfill({json:{found:!body.batch_id||body.batch_id===state.key,rows,counts,active:rows.some(r=>['Pending','Processing'].includes(r.state))}});
  }
  return route.abort();
 });
 await page.goto('https://background-review.local.test/');
 const start=()=>page.evaluate(ids=>postMessage({type:'sports-cave-bulk-products',product_gids:ids},location.origin),ids);
 await start();await page.locator('#grid figure').first().waitFor();return {page,start,errors};
}
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 for(const width of [1280,390]){
  const context=await browser.newContext({viewport:{width,height:800}}),state={submissions:[],polls:0,dropAck:true,previewFailure:true};
  let {page,start,errors}=await fixture(context,state);
  await page.clock.fastForward(1800);
  await page.waitForFunction(()=>[...document.querySelectorAll('#grid input')].some(n=>!n.disabled));
  const boxes=page.locator('#grid input:not(:disabled)');await boxes.nth(0).check();await boxes.nth(1).check();
  await page.locator('#approve').click();await page.locator('#confirm').check();
  const began=Date.now();await page.locator('#accept').click();await page.waitForFunction(()=>handoffs.length===1);
  report.push({width,acknowledgement_lost_reconciled_ms:Date.now()-began,accepted:state.items.length});assert.equal(state.submissions.length,1);
  // Refresh with committed work; session storage restores the same durable request ID.
  state.processing=true;await page.reload();await start();await page.locator('#progress').filter({hasText:'Processing: 2'}).waitFor();
  assert.equal(state.submissions.length,1);assert.equal(await page.locator('small.approving').count(),0,'Processing designs belong only to main list');
  // Closing the popup loses no service-owned state. A new page has no session request, so catalogue recovery is exercised.
  await page.close();({page,start,errors}=await fixture(context,state));
  await page.locator('#progress').filter({hasText:'Processing: 2'}).waitFor();assert.equal(state.submissions.length,1);
  state.complete=true;await page.clock.fastForward(3100);await page.locator('#progress').filter({hasText:'Approved: 1 / Skipped: 0 / Needs Attention: 1'}).waitFor();
  assert.equal(await page.getByText(/Approval result unknown/).count(),0);
  const polls=state.polls;await page.clock.fastForward(30000);assert.equal(state.polls,polls,'Terminal batches stop polling');
  assert.equal(state.submissions.length,1);assert.equal(errors.length,0);await context.close();
 }
 {
  const context=await browser.newContext(),state={submissions:[],polls:0,noCommitFirst:true};
  const {page}=await fixture(context,state);
  await page.locator('#grid input:not(:disabled)').first().check();await page.locator('#approve').click();await page.locator('#confirm').check();await page.locator('#accept').click();
  await page.getByText('Request not recorded yet. Retry submission using the same saved request ID.',{exact:true}).waitFor();
  await page.locator('#retry-approval').click();await page.waitForFunction(()=>handoffs.length===1);
  assert.equal(state.submissions.length,2);assert.equal(state.submissions[0].request_id,state.submissions[1].request_id);assert.equal(state.items.length,1);
  await context.close();
 }
 fs.mkdirSync('output/bulk-v3',{recursive:true});fs.writeFileSync('output/bulk-v3/browser-performance.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 console.log('Preview retry, lost acknowledgement, durable request reconciliation, refresh, popup close, partial progress and terminal polling cleanup passed.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
