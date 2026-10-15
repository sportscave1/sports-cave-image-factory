// Dedicated loopback Streamlit fixture only. Never launches the production app.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const base='http://127.0.0.1:8645';
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:900}});let batches=0;
  page.on('request',r=>{if(r.url().endsWith('/api/auto-editions/status'))batches++;});
  await page.request.post(base+'/fixture-stage',{data:{stage:'Queued'}});
  await page.goto(base);await page.locator('[data-testid=stDataFrame]').waitFor();
  await page.waitForFunction(()=>!!window.SportsCaveEditionStatus);
  const canvas=page.locator('[data-testid=stDataFrame] canvas').first();
  // The native grid remains mounted; its scroll node uses the existing Glide class.
  const scroll=page.locator('.dvn-scroller').first();
  await scroll.evaluate(n=>{n.scrollTop=700;n.scrollLeft=180;});await page.waitForTimeout(50);
  const before=await scroll.evaluate(n=>({top:n.scrollTop,left:n.scrollLeft}));
  const unchanged=await page.evaluate(()=>SportsCaveEditionStatus.poll());
  assert.equal(batches,1);await page.waitForTimeout(100);
  assert((await page.locator('body').innerText()).includes('fixture-main-runs: 1'));
  await page.request.post(base+'/fixture-stage',{data:{stage:'Preparing'}});
  await page.evaluate(()=>{const f=[...document.querySelectorAll('iframe')].find(f=>f.title?.includes('edition_auto_live'));f.contentWindow.Date.now=()=>new Date().getTime()+5000;return SportsCaveEditionStatus.poll();});
  await page.waitForFunction(()=>window.SportsCaveEditionStatusState.nonce>=1);
  await page.waitForTimeout(800);
  assert.equal(batches,2);assert((await page.locator('body').innerText()).includes('fixture-main-runs: 1'),'Status event must rerun only table fragment');
  assert.deepEqual(await scroll.evaluate(n=>({top:n.scrollTop,left:n.scrollLeft})),before);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Page must not gain horizontal overflow');
  assert.equal(await page.locator('.st-key-edition-auto-filter').count(),1);
  assert.equal(await page.locator('[data-testid=stDataFrame]').evaluate(n=>n.getBoundingClientRect().height),600);
  if(width>800){
   const box=await canvas.boundingBox();await page.mouse.dblclick(box.x+420,box.y+49);
   const input=page.locator('.gdg-input');await input.waitFor();await input.fill('42');
   const nonce=await page.evaluate(()=>SportsCaveEditionStatusState.nonce);
   await page.request.post(base+'/fixture-stage',{data:{stage:'Queued'}});
   await page.evaluate(()=>{const f=[...document.querySelectorAll('iframe')].find(f=>f.title?.includes('edition_auto_live'));f.contentWindow.Date.now=()=>new Date().getTime()+10000;return SportsCaveEditionStatus.poll();});
   assert.equal(await input.inputValue(),'42');assert.equal(await page.evaluate(()=>SportsCaveEditionStatusState.nonce),nonce,'Uncommitted native edit must defer refresh');
   await input.press('Enter');await page.getByText('1 unsaved change',{exact:false}).waitFor();
   await page.getByRole('button',{name:'Refresh',exact:true}).click();await page.getByText('1 unsaved change',{exact:false}).waitFor();
   assert((await page.locator('body').innerText()).includes('fixture-main-runs: 1'));
  }
  await page.screenshot({path:`output/v15-phase3/native-${width}.png`});
  await page.close();console.log('Native Streamlit status/scroll layout passed',width);
 }
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
