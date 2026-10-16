// Synthetic intercepted gallery and isolated native editor; no application startup.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});const report=[];try{
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:850}});let active=0,maxActive=0,downloads=0,large=0,approvals=0;
  const rows=Array.from({length:48},(_,n)=>({product_gid:'gid://shopify/Product/'+(n+1),hash:'a'.repeat(64),title:'Synthetic artwork '+(n+1),eligible:n<40,reason:'Needs evidence'}));
  const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==','base64');
  await page.route('**/*',async route=>{const u=new URL(route.request().url());
   if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/auto_editions/bulk.html','utf8')});
   if(u.pathname.endsWith('/list'))return route.fulfill({json:{rows,metadata_queries:2,duration_ms:1}});
   if(u.pathname.endsWith('/image')){if(u.searchParams.has('large'))large++;else downloads++;active++;maxActive=Math.max(active,maxActive);await new Promise(r=>setTimeout(r,15));active--;return route.fulfill({contentType:'image/png',body:png});}
   if(u.pathname.endsWith('/approve')){approvals++;const body=route.request().postDataJSON();assert.equal(body.confirm_visual_quality,true);assert.equal(body.items.length,40);return route.fulfill({json:{counts:{Approved:39,Skipped:1,'Needs Attention':0},results:body.items.map((i,n)=>({product_gid:i.product_gid,result:n?'Approved':'Skipped'})),duration_ms:3}});}
   throw Error('Unexpected request '+u.pathname);
  });
  await page.goto('https://bulk.local.test/');await page.evaluate(()=>window.postMessage({type:'sports-cave-bulk-products',product_gids:['gid://shopify/Product/1']},location.origin));
  await page.waitForFunction(()=>document.querySelectorAll('#grid img').length===48&&reviewTimings.allThumbnailsMs>0);
  assert(maxActive<=3,'Bounded thumbnail requests');assert.equal(downloads,48);assert.equal(large,0);assert.equal(approvals,0);
  assert.equal(await page.locator('#grid input:disabled').count(),8);await page.locator('#grid input').first().check();assert(await page.locator('#approve').isEnabled());
  await page.locator('#grid img').first().click();await page.locator('#large[open]').waitFor();await page.locator('#close-large').click();assert.equal(large,1);
  await page.locator('#select').click();assert.equal(await page.locator('#grid input:checked').count(),40);await page.locator('#all').click();assert.equal(approvals,0);assert(await page.locator('#accept').isDisabled());await page.locator('#confirm').check();await page.locator('#accept').click();await page.getByText('Approved: 39 / Skipped: 1 / Needs Attention: 0',{exact:true}).waitFor();assert.equal(approvals,1);assert.equal(downloads,48);assert.equal(await page.locator('#grid input:checked').count(),0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No mobile overflow');
  const metrics=await page.evaluate(()=>reviewTimings);report.push({width,products:48,maxConcurrentThumbnails:maxActive,...metrics});fs.mkdirSync('output/bulk-review',{recursive:true});await page.screenshot({path:`output/bulk-review/gallery-${width}.png`,fullPage:true});await page.close();
 }
 // Exercise the actual bundled Glide header and Streamlit fragment with synthetic rows.
 for(const width of [1440,390]){
 const page=await browser.newPage({viewport:{width,height:900}});await page.goto('http://127.0.0.1:8645');await page.locator('[data-testid=stDataFrame] canvas').first().waitFor();
 if(width>800){const box=await page.locator('[data-testid=stDataFrame] canvas').first().boundingBox();await page.mouse.dblclick(box.x+420,box.y+49);const input=page.locator('.gdg-input');await input.waitFor();await input.fill('42');await input.press('Enter');await page.getByText('1 unsaved change',{exact:false}).waitFor();}
 const scroll=page.locator('.dvn-scroller').first();await scroll.evaluate(n=>{n.scrollLeft=10000;n.scrollTop=500;});
 const menu=page.getByRole('button',{name:'Auto Editions menu: Bulk Review and Sort by'});await menu.waitFor();
 const before=await page.getByText('fixture-main-runs:',{exact:false}).innerText(),position=await scroll.evaluate(n=>({left:n.scrollLeft,top:n.scrollTop}));
 await menu.click();for(const label of ['Failed First','Not Connected First','Queued First','Needs Review First','Synced / Cloud Ready First','Default Order'])assert(await page.getByRole('menuitem',{name:label,exact:true}).isVisible());
 await page.getByRole('menuitem',{name:'Needs Review First',exact:true}).click();await page.waitForFunction(()=>window.SportsCaveEditionStatusState?.nonce>0);await page.waitForTimeout(1000);
 assert.equal(await page.getByText('fixture-main-runs:',{exact:false}).innerText(),before,'Sorting stays in fragment');assert.deepEqual(await scroll.evaluate(n=>({left:n.scrollLeft,top:n.scrollTop})),position,'Scroll preserved');
 if(width>800)await page.getByText('1 unsaved change',{exact:false}).waitFor();
 await page.close();}
 fs.writeFileSync('output/bulk-review/browser-performance.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));console.log('Bulk gallery desktop/mobile, bounded concurrency, single confirmation, result counts and native header fragment passed.');
 }finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
