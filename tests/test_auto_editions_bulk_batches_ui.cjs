// Isolated 47-design HTTP fixture. No production data, cookies or credentials.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==','base64');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const output='output/bulk-backlog-review';
async function fixture(browser,html,width=1440,before=false){
 const page=await browser.newPage({viewport:{width,height:850}}),items=Array.from({length:47},(_,i)=>({product_gid:'gid://shopify/Product/'+(i+1),hash:'a'.repeat(64),title:'Synthetic '+(i+1),eligible:true,reason:''}));
 const state={lists:0,previewIds:new Set(),bytes:0,errors:[],failList:false,failImage:false,approved:new Set(),active:0,maxActive:0,approvals:[],change:false};
 page.on('pageerror',e=>state.errors.push(e.message));
 await page.route('**/*',async r=>{
  const u=new URL(r.request().url());if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:html});
  if(u.pathname.endsWith('/list')){
   state.lists++;if(state.failList){state.failList=false;return r.fulfill({status:503,json:{error:'Temporary metadata failure. Retry.'}});}
   const b=r.request().postDataJSON(),size=before?20:10,candidates=items.map((v,i)=>({...v,position:i+1})).filter(v=>!state.approved.has(v.product_gid)),remaining=candidates.filter(v=>v.position>b.cursor),rows=remaining.slice(0,size);
   await sleep(30);return r.fulfill({json:{rows,next_cursor:remaining.length>size?rows.at(-1).position:null,total_remaining:candidates.length,duration_ms:30}});
  }
  if(u.pathname.endsWith('/previews')){
   const b=r.request().postDataJSON();assert(b.items.length<=8);for(const i of b.items)state.previewIds.add(i.product_gid);
   state.active++;state.maxActive=Math.max(state.maxActive,state.active);await sleep(35);state.active--;
   const rows=b.items.map(i=>({...i,...(state.failImage&&i.product_gid===items[0].product_gid?{state:'Unavailable',error:'Embedded ICC profile required.'}:{jpeg:png.toString('base64')})}));
   state.bytes+=rows.filter(i=>i.jpeg).length*png.length;return r.fulfill({json:{rows}});
  }
  if(u.pathname.endsWith('/image')){state.bytes+=png.length;return r.fulfill({contentType:'image/png',body:png});}
  if(u.pathname.endsWith('/progress'))return r.fulfill({json:{found:true,active:false,rows:[],counts:{Pending:0,Processing:0,Approved:0,Skipped:0,'Needs Attention':0,Failed:0}}});
  if(u.pathname.endsWith('/approve')){const b=r.request().postDataJSON();state.approvals.push(b);return r.fulfill({status:202,json:{accepted:true,batch_id:b.request_id}});}
  throw Error(u.pathname);
 });
 const start=performance.now();await page.goto('https://batch.local.test/');await page.evaluate(ids=>postMessage({type:'sports-cave-bulk-products',product_gids:ids},location.origin),items.map(i=>i.product_gid));
 await page.locator('#grid figure').first().waitFor();await page.locator('#grid input:not(:disabled)').first().waitFor();
 const first=performance.now()-start;
 return {page,state,items,first};
}
async function resolveBatch(page){for(const card of await page.locator('#grid figure').all()){await card.scrollIntoViewIfNeeded();await card.locator('input:not(:disabled)').waitFor();}}
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true}),report=[];try{
 const current=fs.readFileSync('components/auto_editions/bulk.html','utf8'),old=fs.readFileSync(output+'/before/components/auto_editions/bulk.html','utf8');
 for(const before of [true,false]){
  const {page,state,first}=await fixture(browser,before?old:current,1440,before);
  await page.waitForFunction(()=>reviewTimings.firstViewportResolvedMs!==undefined);await page.waitForTimeout(200);const initial=await page.locator('#grid figure').count(),automaticDesigns=state.previewIds.size,automaticBytes=state.bytes,initialTimings=await page.evaluate(()=>({...reviewTimings}));
  if(before){while(await page.locator('#grid figure').count()<47){await page.locator('#more').scrollIntoViewIfNeeded();await sleep(80);}await resolveBatch(page);}
  else{await resolveBatch(page);await page.screenshot({path:output+'/local-batch-10.png'});assert.equal(await page.locator('#grid figure').count(),10);assert.equal(state.lists,1);assert([...state.previewIds].every(p=>Number(p.split('/').at(-1))<=10));}
  report.push({scope:'Synthetic identical 47-design fixture; 1px image payload, 30ms metadata / 35ms preview delay; no provider timings',before,first_usable_ms:+first.toFixed(2),initial_cards:initial,metadata_requests:state.lists,automatic_preview_designs:automaticDesigns,automatic_image_payload_bytes:automaticBytes,cumulative_designs_after_scrolling:state.previewIds.size,cumulative_image_payload_bytes_after_scrolling:state.bytes,maximum_preview_requests:state.maxActive,initial_timings:initialTimings});
  assert.equal(state.errors.length,0);await page.close();
 }
 for(const width of [1440,390]){
  const {page,state,items}=await fixture(browser,current,width);await resolveBatch(page);await page.locator('#select').click();assert.equal(await page.locator('#grid input:checked').count(),10);
  await page.locator('#next').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/11'));await resolveBatch(page);assert.equal(await page.locator('#grid input:checked').count(),0);
  await page.locator('#previous').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/1'));await resolveBatch(page);assert.equal(await page.locator('#grid input:checked').count(),10);
  await page.locator('#approve').click();assert((await page.locator('#confirmation').innerText()).includes('10 designs in this batch'));assert.equal(state.approvals.length,0);await page.locator('#cancel').click();
  // A changed preparation loses its saved selection on returning to the batch.
  await page.locator('#next').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/11'));items[0].hash='b'.repeat(64);
  await page.locator('#previous').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/1'));await resolveBatch(page);assert.equal(await page.locator('#grid input:checked').count(),9);
  state.failList=true;await page.locator('#next').click();await page.getByText('Temporary metadata failure. Retry.',{exact:true}).waitFor();const n=state.lists;await sleep(150);assert.equal(state.lists,n);await page.locator('#retry').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/11'));
  await page.locator('#previous').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/1'));await resolveBatch(page);
  state.approved.add(items[0].product_gid);
  await page.evaluate(item=>showProgress({active:false,counts:{Pending:0,Processing:0,Approved:1,Skipped:0,'Needs Attention':0,Failed:0},rows:[{...item,state:'Approved',current_hash:item.hash,current_status:'Cloud Ready',reason:''}]},false),items[0]);
  await page.waitForFunction(()=>document.querySelectorAll('#grid figure').length===10&&document.querySelector('#grid input').value.endsWith('/2'));
  assert((await page.locator('#batch-count').innerText()).includes('46 remaining / 47 total'));
  await page.locator('#grid input:not(:disabled)').first().waitFor();await page.locator('#grid img').first().click();await page.locator('#large-image').waitFor({state:'visible'});await page.locator('#close-large').click();
  assert.equal(state.errors.length,0);assert(state.maxActive<=2);assert.equal(state.approvals.length,0);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.close();
 }
 {
  const {page,state}=await fixture(browser,current);state.failImage=true;await page.locator('#reload').click();await page.getByText('Embedded ICC profile required.',{exact:true}).waitFor();assert(await page.locator('#grid input').first().isDisabled());state.failImage=false;await page.locator('#grid figure').first().getByRole('button',{name:'Retry Preview'}).click();await page.locator('#grid input:not(:disabled)').first().waitFor();assert.equal(state.approvals.length,0);await page.close();
 }
 fs.writeFileSync(output+'/pagination-measurements.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));console.log('Ten-card navigation, scoped selection, stale selection, gap fill, counts, desktop/mobile, detail, metadata retry and ICC retry passed.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
