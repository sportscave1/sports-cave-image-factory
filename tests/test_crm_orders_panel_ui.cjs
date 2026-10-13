// Real Streamlit page/fragment and shared table, with loopback PostgreSQL facts.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const b=await chromium.launch({channel:'chrome',headless:true}),report=[];
 try{for(const width of [1440,390]){
  const p=await b.newPage({viewport:{width,height:1000}});
  await p.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await p.goto('http://127.0.0.1:18738');
  const exp=p.locator('[data-testid="stExpander"] details').first();
  const start=Date.now();await p.getByText('Orders',{exact:true}).click();
  const f=p.frameLocator('iframe[title="crm_lifecycle_ui.crm_checkout_table"]');
  await f.locator('tbody tr').first().waitFor({timeout:30000});const opening=Date.now()-start;
  await p.screenshot({path:'.tmp-preview-performance/orders-toolbar-'+width+'.png',fullPage:true});
  const names=await f.locator('thead th').allTextContents();
  assert.deepEqual(names,['','Customer','Order date','Order','Fulfilment','Flow','Email 1','Email 2','Email 3']);
  assert.equal(await p.getByRole('button',{name:'Refresh audience',exact:true}).count(),0);
  assert.equal(await p.getByRole('button',{name:'Clear selection',exact:true}).count(),0);
  assert.equal(await p.getByText(/orders selected/).count(),0);
  await p.evaluate(()=>{window.panelMonitor={closures:0,remounts:0};window.observedFrame=document.querySelector('iframe[title="crm_lifecycle_ui.crm_checkout_table"]');new MutationObserver(()=>{
   if(!document.querySelector('[data-testid="stExpander"] details')?.open)window.panelMonitor.closures++;
   const frame=document.querySelector('iframe[title="crm_lifecycle_ui.crm_checkout_table"]');if(frame&&frame!==window.observedFrame){window.panelMonitor.remounts++;window.observedFrame=frame;}
  }).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['open']});});
  const check=f.locator('tbody input').first(),selectedStart=Date.now();await check.check();
  await f.locator('tbody input').nth(1).check();
  await p.waitForTimeout(300);assert.equal(await f.locator('tbody input:checked').count(),2);
  const selectionMs=Date.now()-selectedStart;
  await f.locator('thead input').check();await p.waitForTimeout(300);assert.equal(await f.locator('tbody input:checked').count(),50);
  await p.getByRole('button',{name:'Next',exact:true}).click();await f.locator('tbody tr').nth(5).waitFor({state:'detached'});
  await f.locator('thead input').check();await p.waitForTimeout(300);await f.locator('thead input').uncheck();await p.waitForTimeout(300);
  await p.getByRole('button',{name:'Previous',exact:true}).click();await f.locator('tbody tr').nth(49).waitFor();
  assert.equal(await f.locator('tbody input:checked').count(),0);
  const search=p.getByRole('textbox',{name:'Search and filter',exact:true});
  const prefix=await search.inputValue();
  await search.fill(prefix+'-0@');await search.press('Enter');await f.locator('tbody tr').nth(1).waitFor({state:'detached'});await f.getByRole('button',{name:'Details Fixture purchaser 0',exact:true}).waitFor();
  assert.equal(await f.locator('tbody tr').count(),1);
  await search.fill(prefix);await search.press('Enter');await f.locator('tbody tr').nth(49).waitFor();
  await p.getByRole('combobox',{name:'Status',exact:true}).click();await p.getByRole('option',{name:'Paid',exact:true}).click();await f.locator('tbody tr').nth(49).waitFor();
  await p.getByRole('combobox',{name:'Sort',exact:true}).click();await p.getByRole('option',{name:'Oldest',exact:true}).click();await f.locator('tbody tr').nth(49).waitFor();
  await p.getByRole('combobox',{name:'Sort',exact:true}).click();await p.getByRole('option',{name:'Newest',exact:true}).click();await f.locator('tbody tr').nth(49).waitFor();
  await p.getByRole('button',{name:/Date filters/}).click();
  for(const [part,value] of [['year','2030'],['month','01'],['day','01']]){
   const segment=p.getByRole('spinbutton',{name:part+', From',exact:true});await segment.click();await segment.pressSequentially(value);
  }
  await p.keyboard.press('Tab');await p.keyboard.press('Escape');
  await f.getByText('No matching orders',{exact:true}).waitFor();
  await p.getByRole('button',{name:/Date filters/}).click();const year=p.getByRole('spinbutton',{name:'year, From',exact:true});await year.click();for(let n=0;n<10;n++)await year.press('ArrowDown');for(let n=0;n<3;n++)await p.keyboard.press('Tab');
  await f.locator('tbody tr').nth(49).waitFor();await p.keyboard.press('Escape');
  await f.getByRole('button',{name:'Details Fixture purchaser 0',exact:true}).click();await p.getByText('Order and product history',{exact:true}).waitFor();
  assert.match(await p.locator('body').innerText(),/Marketing consent: SUBSCRIBED/);
  await check.check();await p.getByRole('button',{name:'Add to Flow',exact:true}).click();
  await p.getByRole('dialog').waitFor();assert.match(await p.getByRole('dialog').innerText(),/freshly verify marketing consent/);
  await p.getByRole('button',{name:'Cancel',exact:true}).click();await p.getByRole('dialog').waitFor({state:'hidden'});await f.locator('tbody tr').nth(49).waitFor();
  assert.equal(await exp.getAttribute('open'),'');
  if(width===1440){
   const positions=await p.locator('.st-key-post-purchase-toolbar').locator('input[aria-label="Search and filter"],[role="combobox"],button').evaluateAll(xs=>xs.filter(x=>x.getClientRects().length).map(x=>({top:x.getBoundingClientRect().top,bottom:x.getBoundingClientRect().bottom})));
   assert.ok(Math.max(...positions.map(x=>x.top))-Math.min(...positions.map(x=>x.top))<5,JSON.stringify(positions));
   assert.ok(positions.every(x=>x.bottom-x.top<=34),JSON.stringify(positions));
   assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   const frame=p.frames().find(fr=>fr.url().includes('crm_checkout_table'));
   await frame.locator('.wrap').evaluate(el=>el.scrollTop=220);
   await p.getByRole('button',{name:'Fixture background order update',exact:true}).click();
   await f.getByText('Fulfilled',{exact:true}).first().waitFor({timeout:45000});
   await frame.locator('.wrap').evaluate(el=>el.scrollTop=220);
   console.log(JSON.stringify({phase:'idle-start',width,openingMs:opening,selectionMs}));
   await p.waitForTimeout(process.env.CRM_ORDERS_QUICK==='1'?1000:185000);
   assert.equal(await exp.getAttribute('open'),'');
   assert.equal(await frame.locator('.wrap').evaluate(el=>el.scrollTop),220);
   assert.equal(await f.locator('tbody input:checked').count(),1);
   const monitor=await p.evaluate(()=>window.panelMonitor);assert.equal(monitor.closures,0);assert.equal(monitor.remounts,0);
   console.log(JSON.stringify({phase:'idle-complete',width,monitor}));
  }
  await p.screenshot({path:'.tmp-preview-performance/orders-'+width+'.png',fullPage:true});
  await p.getByText('Orders',{exact:true}).click();await p.waitForTimeout(width===1440&&process.env.CRM_ORDERS_QUICK!=='1'?35000:1000);
  assert.equal(await exp.getAttribute('open'),null);
  assert.equal(await p.locator('[data-testid="stException"]').count(),0);
  const metrics=JSON.parse(await p.locator('.st-key-fixture-metrics').innerText());
  const reopen=Date.now();await p.getByText('Orders',{exact:true}).click();await f.locator('tbody tr').nth(49).waitFor();const warmMs=Date.now()-reopen;
  report.push({width,openingMs:opening,warmMs,selectionMs,metrics});await p.close();
 }}finally{await b.close();}
 require('node:fs').writeFileSync('.tmp-preview-performance/orders-panel-browser.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exit(1)});
