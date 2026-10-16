// Intercepted synthetic cards: bounded cache-only prefetch, cancellation and selection.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const html=fs.readFileSync('components/auto_editions/bulk.html','utf8'),jpeg='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==';
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});let release=[];try{
 const page=await browser.newPage({viewport:{width:390,height:500}}),calls=[],failures=[];let imageRequests=0;
 const catalogue=Array.from({length:60},(_,n)=>({product_gid:'gid://shopify/Product/'+(n+1),hash:'a'.repeat(64),title:'Synthetic '+(n+1),eligible:true,reason:''}));
 page.on('requestfailed',r=>{if(r.url().endsWith('/previews'))failures.push(r.url());});
 await page.route('**/*',async route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/')return route.fulfill({contentType:'text/html',body:html});
  if(path.endsWith('/list')){const cursor=route.request().postDataJSON().cursor;return route.fulfill({json:{rows:catalogue.slice(cursor,cursor+10),next_cursor:cursor+10<60?cursor+10:null}});}
  if(path.endsWith('/progress'))return route.fulfill({json:{found:false,rows:[],active:false}});
  if(path.endsWith('/image')){imageRequests++;return route.fulfill({status:500,json:{error:'Unexpected speculative fallback'}});}
  if(path.endsWith('/previews')){
   const body=route.request().postDataJSON();calls.push(body);
   const answer=()=>route.fulfill({json:{rows:body.items.map(i=>({...i,jpeg}))}}).catch(()=>{});
   if(body.prefetch)return new Promise(done=>release.push(async()=>{await answer();done();}));
   return answer();
  }
  return route.abort();
 });
 await page.goto('https://thumbnail-priority.local.test/');await page.evaluate(ids=>postMessage({type:'sports-cave-bulk-products',product_gids:ids},location.origin),catalogue.map(r=>r.product_gid));
 await page.locator('#grid input:not(:disabled)').first().waitFor();for(let n=0;n<100&&!calls.some(c=>c.prefetch);n++)await page.waitForTimeout(20);
 assert(calls.some(c=>c.prefetch));assert(calls.filter(c=>c.prefetch).every(c=>c.items.length<=4));
 const first=page.locator('#grid input').first();await first.check();const selectedID=await first.inputValue();
 await page.locator('#next').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/11'));await page.locator('#grid figure').nth(9).scrollIntoViewIfNeeded();
 await page.locator('#grid figure').nth(9).locator('input:not(:disabled)').waitFor();
 assert(calls.some(c=>!c.prefetch&&c.items.some(i=>i.product_gid.endsWith('/20'))),'Visible requests bypass a stalled speculative slot');
 await page.waitForFunction(()=>activeSpeculative===0);assert(failures.length>0,'Unneeded speculative HTTP work was aborted');
 assert.equal(imageRequests,0);
 await page.locator('#previous').click();await page.waitForFunction(()=>document.querySelector('#grid input')?.value.endsWith('/1'));assert(await page.locator('#grid input[value="'+selectedID+'"]').isChecked());
 const scroll=await page.evaluate(()=>scrollY);for(const done of release)await done();release=[];
 await page.waitForTimeout(50);assert.equal(await page.evaluate(()=>scrollY),scroll);
 console.log('Visible priority, four-card cache-only prefetch, speculative abort, scroll and selection preservation passed');
 await page.close();
}finally{for(const done of release)await done();await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
