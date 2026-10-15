// Real native grid, isolated synthetic loopback fixture. No live app or account.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const base='http://127.0.0.1:8645';
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:900}});let resets=[],batches=0,release;
  page.on('request',request=>{if(request.url().endsWith('/api/auto-editions/status'))batches++;});
  await page.route('**/api/auto-editions/status/reset',async route=>{
   resets.push(route.request().postDataJSON());
   await new Promise(resolve=>{release=resolve;});
   await route.fulfill({json:{ok:true,stage:'Discovering'}});
  });
  await page.request.post(base+'/fixture-stage',{data:{stage:'Queued'}});
  await page.goto(base);await page.locator('[data-testid=stDataFrame] canvas').first().waitFor();
  const grid=page.locator('[data-testid=stDataFrame]'),scroll=page.locator('.dvn-scroller').first();
  if(width<800)await scroll.evaluate(n=>n.scrollLeft=10000);
  await page.locator('.sc-auto-reset:not(:disabled)').first().waitFor();
  assert.equal(await grid.evaluate(n=>n.getBoundingClientRect().height),600);
  assert((await page.locator('.sc-auto-reset').count())<=24,'Only visible rows get buttons');
  // Exercise actual native editing; reset/cancel must preserve its dirty buffer.
  if(width>800){
   const canvas=grid.locator('canvas').first(),box=await canvas.boundingBox();
   await page.mouse.dblclick(box.x+420,box.y+49);const input=page.locator('.gdg-input');await input.waitFor();await input.fill('42');await input.press('Enter');
   await page.getByText('1 unsaved change',{exact:false}).waitFor();
  }
  await scroll.evaluate(n=>{n.scrollTop=700;n.scrollLeft=10000;});
  await page.waitForTimeout(150);
  const position=await scroll.evaluate(n=>({top:n.scrollTop,left:n.scrollLeft}));
  let icon=page.locator('.sc-auto-reset:not(:disabled)').first();await icon.waitFor();
  const pid=await icon.getAttribute('data-product-gid');assert.notEqual(pid,'gid://shopify/Product/1','Scrolled row identity must be current');
  await icon.click();const modal=page.getByRole('dialog',{name:'Reset design?',exact:true});await modal.waitFor();
  assert.equal(await modal.locator('p').innerText(),'Reset design?');assert.equal(await modal.getByRole('button').count(),2);
  assert((await modal.boundingBox()).height<130,'Compact popup');assert((await modal.boundingBox()).width<270);
  await page.screenshot({path:`output/reset/popup-${width}.png`});
  await modal.getByRole('button',{name:'Cancel',exact:true}).click();assert.equal(await page.getByRole('dialog').count(),0);assert.equal(resets.length,0);
  assert.deepEqual(await scroll.evaluate(n=>({top:n.scrollTop,left:n.scrollLeft})),position);
  const before=batches;await icon.click();await modal.getByRole('button',{name:'Reset',exact:true}).click();
  assert.equal(await page.getByRole('dialog').count(),0,'Popup closes before network completion');
  await page.waitForFunction(()=>sessionStorage.length>0);assert.equal(resets.length,1);assert.equal(resets[0].product_gid,pid);assert.match(resets[0].request_id,/^[0-9a-f-]{36}$/);
  release();await page.waitForFunction(()=>![...Object.keys(sessionStorage)].some(k=>k.startsWith('sc-design-reset:')));
  await page.waitForTimeout(200);assert.equal(batches,before+1,'One lightweight batch refresh after reset');
  assert.deepEqual(await scroll.evaluate(n=>({top:n.scrollTop,left:n.scrollLeft})),position);
  if(width>800)await page.getByText('1 unsaved change',{exact:false}).waitFor();
  assert((await page.locator('body').innerText()).includes('fixture-main-runs: 1'),'No whole-page rerun');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  const counts=await page.evaluate(()=>({columns:document.querySelectorAll('[data-testid="stDataFrame"]').length,buttons:document.querySelectorAll('.sc-auto-reset').length}));assert.equal(counts.columns,1);
  await page.close();console.log('Reset native-grid popup, identity, cancel, immediate close, edits and scrolling passed',width);
 }
 // A reset completing during an older status read must cause one fresh read,
 // rather than waiting for the next 25-second timer or flashing stale data.
 const race=await browser.newPage();let reads=0,releaseOld;
 const value=status=>({product_gid:'gid://shopify/Product/987',status});
 await race.route('**/*',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/')return route.fulfill({contentType:'text/html',body:'<div class="st-key-edition-workspace" style="height:200px"><div data-testid="stDataFrame"></div></div><iframe id="bridge" src="/live"></iframe><script>window.events=[];addEventListener("message",e=>{if(e.data.type==="streamlit:setComponentValue")events.push(e.data.value)})</script>'});
  if(path==='/live')return route.fulfill({contentType:'text/html',body:'<script>'+fs.readFileSync('components/edition_auto_status/live.js','utf8')+'</script>'});
  if(path==='/api/auto-editions/status'){
   reads++;const stage=reads===1?'Queued':'Preparing';
   if(reads===1)await new Promise(resolve=>{releaseOld=resolve;});
   return route.fulfill({json:{rows:[value(stage)],snapshot:{actor_id:'synthetic',issued_at:Date.now()/1000},signature:'synthetic'}});
  }return route.abort();
 });
 await race.goto('https://reset-refresh.local.test/');await race.waitForFunction(()=>!!SportsCaveEditionStatus);
 await race.evaluate(row=>document.querySelector('#bridge').contentWindow.postMessage({type:'streamlit:render',args:{product_gids:[row.product_gid],rows:[row]}},location.origin),value('Queued'));
 await race.waitForTimeout(30);await race.evaluate(()=>{window.oldPoll=SportsCaveEditionStatus.poll();});
 while(!releaseOld)await race.waitForTimeout(10);
 await race.evaluate(()=>SportsCaveEditionStatus.refresh());releaseOld();
 await race.waitForFunction(()=>events.length===1&&events[0].rows[0].status==='Preparing');assert.equal(reads,2);
 await race.close();console.log('Concurrent reset/status refresh coalesces into one fresh batch without a stale update.');
}finally{await browser.close();}})().catch(error=>{console.error(error);process.exitCode=1;});
