// Real native grid, isolated synthetic loopback fixture. No live app or account.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const base='http://127.0.0.1:8645';
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:900}});let resets=[],batches=0,release,blocked=false;
  page.on('request',request=>{if(request.url().endsWith('/api/auto-editions/status'))batches++;});
  await page.route('**/api/auto-editions/status/reset',async route=>{
   resets.push(route.request().postDataJSON());
   if(blocked)return route.fulfill({status:409,json:{error:'This design is currently approving. Wait for approval recovery to finish before resetting.'}});
   await new Promise(resolve=>{release=resolve;});
   await page.request.post(base+'/fixture-stage',{data:{stage:'Queued',mapping_overrides:{[resets.at(-1).product_gid]:null}}});
   await route.fulfill({json:{ok:true,stage:'Complete'}});
  });
  await page.request.post(base+'/fixture-stage',{data:{stage:'Queued',mapping_overrides:{}}});
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
  assert((await modal.locator('p').innerText()).includes('clear its PSD mapping'));assert((await modal.locator('p').innerText()).includes('enter the PSD name again using Add'));assert.equal(await modal.getByRole('button').count(),2);
  assert((await modal.boundingBox()).height<230,'Compact popup');assert((await modal.boundingBox()).width<270);
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
  const fileForPid=pid=>{const canvas=document.querySelector('[data-testid=stDataFrame] canvas');if(!canvas)return null;const key=Object.keys(canvas).find(k=>k.startsWith('__reactFiber'));let fiber=canvas[key];if(!fiber)return null;let root=fiber;while(root.return)root=root.return;if(root.stateNode?.current!==root&&fiber.alternate)fiber=fiber.alternate;for(let n=0;fiber&&n<25;n++,fiber=fiber.return){const p=fiber.memoizedProps;if(!p?.columns||typeof p.getCellContent!=='function')continue;const a=p.columns.findIndex(c=>c.title==='Auto Editions'),f=p.columns.findIndex(c=>c.title==='File');if(a<0||f<0)continue;for(let row=0;row<p.rows;row++){try{if(new URL(p.getCellContent([a,row]).data,location.href).searchParams.get('product_gid')===pid)return p.getCellContent([f,row]).data;}catch{}}}return null;};
  await page.waitForFunction(({pid,code})=>eval('('+code+')')(pid)?.endsWith('#Add'),{pid,code:fileForPid.toString()});
  blocked=true;icon=page.locator('.sc-auto-reset[data-product-gid="'+pid+'"]');await icon.click();await page.getByRole('dialog',{name:'Reset design?',exact:true}).getByRole('button',{name:'Reset',exact:true}).click();
  await page.getByRole('dialog',{name:'Reset unavailable',exact:true}).getByText('This design is currently approving.',{exact:false}).waitFor();await page.getByRole('dialog',{name:'Reset unavailable',exact:true}).getByRole('button',{name:'Close',exact:true}).click();
  await page.reload();await page.locator('[data-testid=stDataFrame] canvas').first().waitFor();await page.waitForFunction(({pid,code})=>eval('('+code+')')(pid)?.endsWith('#Add'),{pid,code:fileForPid.toString()});
  await page.close();console.log('Reset native grid, mapping cleared to Add, reload, blocked reason, edits and scroll preservation passed',width);
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
