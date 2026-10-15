// All requests are intercepted synthetic responses; no live app/accounts/assets.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const bridge=fs.readFileSync('components/edition_auto_status/live.js','utf8');
const modal=fs.readFileSync('components/auto_editions/status.html','utf8');
const picker=fs.readFileSync('components/psd_picker/index.html','utf8');
const onboarding=fs.readFileSync('components/auto_editions/onboarding.html','utf8');
const PID='gid://shopify/Product/987';
const row=state=>({product_gid:PID,status:state,icon:state==='Cloud Ready'?'✅':'◷',reason:state==='Review'?'Visual review required':'',checkpoint:'Queued',checkpoint_at:'now',preparation_hash:'a'.repeat(64),actions:state==='Review'?['review']:[]});
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});let scenarios=0;
try{
 for(const width of [1280,390]){
  const page=await browser.newPage({viewport:{width,height:800}});let current='Queued',calls=0;
  await page.route('**/*',route=>{
   const u=new URL(route.request().url());if(u.hostname!=='edition-ui.local.test')return route.abort();
   if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:`<style>body{margin:0}.st-key-edition-workspace{height:740px}.scroll{width:95vw;height:500px;overflow:auto}.content{width:1300px;height:1800px}td{height:28px;padding:0 4px}dialog{max-width:94vw}</style><div class="st-key-edition-workspace"><input id="edit" value="37"><div data-testid="stDataFrame"><div class="scroll"><div class="content"><table><thead><tr><th>Product Title</th><th>Next Edition #</th><th>Limit</th><th>Status</th><th>File</th><th>Auto Editions</th></tr></thead><tbody><tr><td>Test Art</td><td>37</td><td>100</td><td>Live</td><td>Add</td><td><a href="/auto-editions/status?product_gid=${encodeURIComponent(PID)}">◷ Queued</a></td></tr></tbody></table></div></div></div></div><iframe id="picker" src="/picker" style="height:0;border:0"></iframe><iframe id="live" src="/live" style="height:0;border:0"></iframe><script>window.events=[];addEventListener('message',e=>{if(e.data?.type==='streamlit:setComponentValue')events.push(e.data.value)});</script>`});
   if(u.pathname==='/picker')return route.fulfill({contentType:'text/html',body:picker});
   if(u.pathname.endsWith('/inline.js'))return route.fulfill({contentType:'text/javascript',body:''});
   if(u.pathname==='/live')return route.fulfill({contentType:'text/html',body:'<script>'+bridge+'</script>'});
   if(u.pathname==='/auto-editions/status')return route.fulfill({contentType:'text/html',body:modal});
   if(u.pathname==='/auto-editions/onboarding')return route.fulfill({contentType:'text/html',body:onboarding});
   if(u.pathname==='/api/auto-editions/status'){calls++;return route.fulfill({json:{rows:[row(current)],snapshot:{rows:[row(current)],actor_id:'admin',issued_at:Date.now()/1000},signature:'synthetic'}});}
   if(u.pathname==='/api/auto-editions/onboarding')return route.fulfill({json:{rows:[{...row('Review'),status:'Blocked',product_title:'Test Art'}],mapped:1,host:{connected:0,last_seen:null}}});
   if(u.pathname.endsWith('/preview'))return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="120"><rect width="200" height="120" fill="#ddd"/></svg>'});
   if(u.pathname.endsWith('/approve')){current='Cloud Ready';return route.fulfill({json:{status:current}});}
   return route.fulfill({status:404});
  });
  await page.goto('https://edition-ui.local.test/');await page.waitForFunction(()=>!!window.SportsCaveEditionStatus);
  await page.evaluate(({PID,row})=>document.querySelector('#live').contentWindow.postMessage({type:'streamlit:render',args:{product_gids:[PID],rows:[row]}},location.origin),{PID,row:row('Queued')});
  assert.equal(calls,0,'Initial server snapshot must not be fetched twice');
  await page.evaluate(()=>window.SportsCaveEditionStatus.poll());assert.equal(calls,1);assert.equal(await page.evaluate(()=>events.length),0,'Unchanged poll must not rerender');
  await page.locator('#edit').fill('42');current='Preparing';
  await page.evaluate(()=>{const w=document.querySelector('#live').contentWindow;w.Date.now=()=>new Date().getTime()+5000;return SportsCaveEditionStatus.poll();});
  assert.equal(await page.evaluate(()=>events.length),0,'Active cell edit must defer status update');assert.equal(await page.locator('#edit').inputValue(),'42');
  await page.locator('th').first().click();await page.waitForFunction(()=>events.length===1);
  assert.equal(await page.locator('#edit').inputValue(),'42');
  await page.evaluate(()=>{const n=document.querySelector('.scroll');n.dispatchEvent(new WheelEvent('wheel',{bubbles:true}));n.scrollTop=680;n.scrollLeft=220;});
  await page.waitForTimeout(40);
  const horizontal=await page.locator('.scroll').evaluate(n=>n.scrollLeft);
  await page.evaluate(()=>document.querySelector('#live').contentWindow.postMessage({type:'streamlit:render',args:{product_gids:['gid://shopify/Product/987'],rows:events[0].rows}},location.origin));
  await page.waitForTimeout(40);assert.equal(await page.locator('.scroll').evaluate(n=>n.scrollTop),680);
  // Scroll position is restored synchronously if Streamlit replaces the grid node.
  await page.evaluate(()=>{const n=document.querySelector('.scroll');n.replaceWith(n.cloneNode(true));});
  await page.waitForTimeout(40);assert.equal(await page.locator('.scroll').evaluate(n=>n.scrollLeft),horizontal);
  current='Review';await page.locator('.scroll').evaluate(n=>{n.scrollTop=0;n.scrollLeft=0;});
  await page.locator('a').click();await page.getByRole('dialog',{name:'Auto Editions',exact:true}).waitFor();
  const detail=page.frameLocator('dialog iframe');await detail.locator('#stage').getByText('Review',{exact:false}).waitFor();
  const before=calls;await page.evaluate(()=>SportsCaveEditionStatus.poll());assert.equal(calls,before,'Parent polling pauses while modal performs scoped reads');
  await detail.getByRole('button',{name:'Review',exact:true}).click();const review=detail.frameLocator('#review');
  await review.getByRole('button',{name:'Approve preview downloads'}).waitFor();assert.equal(await review.getByRole('button',{name:'Approve preview downloads'}).isEnabled(),false);
  assert.equal(await review.locator('#resume').isVisible(),false);
  await review.locator('#confirm').check();await review.getByRole('button',{name:'Approve preview downloads'}).click();
  await detail.locator('#stage').getByText('Cloud Ready',{exact:false}).waitFor();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.getByRole('button',{name:'Close',exact:true}).click();assert.equal(page.url(),'https://edition-ui.local.test/');
  assert.equal(await page.locator('#edit').inputValue(),'42');
  assert.equal(await page.locator('tbody tr').evaluate(n=>n.getBoundingClientRect().height),28);
  scenarios++;await page.close();
 }
 console.log('Auto Editions UI: '+scenarios+' desktop/mobile scenarios passed; edit/scroll/modal preservation, compact review, zero unchanged rerenders, one batch per poll.');
}finally{await browser.close();}})().catch(error=>{console.error(error);process.exitCode=1;});
