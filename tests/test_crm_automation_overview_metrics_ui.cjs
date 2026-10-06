// Run after the loopback overview-metrics SQL tests and preview fixture (8533).
const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage();await page.setViewportSize({width:1366,height:900});await page.goto('http://127.0.0.1:8533');
 const search=page.getByRole('textbox',{name:'Search automations',exact:true});await search.fill('Overview metrics');await search.press('Enter');
 await page.locator('.sc-auto-row').filter({hasText:'Overview metrics counted fixture'}).getByText('2 (12.5%)',{exact:true}).waitFor();
 assert.deepEqual(await page.locator('.sc-auto-head>div').allTextContents(),['Automation','Trigger','Entered','Sent','Delivery %','Opens','Click %','Conversions','Bounce rate','Status']);
 const counted=page.locator('.sc-auto-row').filter({hasText:'Overview metrics counted fixture'});
 assert.equal(await counted.locator('>div').nth(8).innerText(),'4.2%');
 assert.equal(await page.locator('.sc-auto-row').filter({hasText:'Overview metrics zero fixture'}).locator('>div').nth(5).innerText(),'0 (0.0%)');
 const draft=page.locator('.sc-auto-row').filter({hasText:'Overview metrics draft fixture'});
 for(const i of [4,5,6,8])assert.equal(await draft.locator('>div').nth(i).innerText(),'—');
 assert.equal(await page.locator('.sc-auto-head').getByText('Revenue',{exact:true}).count(),0);
 for(const width of [1920,1366,1100,750,390,320]){
  await page.setViewportSize({width,height:950});
  await page.locator('[class*="st-key-auto-actions-"] button:visible').first().scrollIntoViewIfNeeded();
  const geometry=await page.evaluate(()=>{
   const header=document.querySelector('.sc-auto-head'),row=document.querySelector('.sc-auto-row');
   const center=e=>{const r=e.getBoundingClientRect();return r.x+r.width/2};
   const cells=[...header.children].map((h,i)=>({visible:getComputedStyle(h).display!=='none',delta:Math.abs(center(h)-center(row.children[i])),align:getComputedStyle(row.children[i]).textAlign,headAlign:getComputedStyle(h).textAlign}));
   const actions=document.querySelector('.sc-auto-actions-heading'),button=[...document.querySelectorAll('[class*="st-key-auto-actions-"] button')].find(e=>e.getClientRects().length);
   return {cells,actionDelta:Math.abs(center(actions)-center(button)),grids:[getComputedStyle(header).gridTemplateColumns,getComputedStyle(row).gridTemplateColumns],overflow:document.documentElement.scrollWidth>innerWidth+2};
  });
  assert.equal(geometry.grids[0],geometry.grids[1]);assert.equal(geometry.overflow,false);
  for(const [i,c] of geometry.cells.entries())if(c.visible){assert.ok(c.delta<1,JSON.stringify(geometry));if(i>=2){assert.equal(c.align,'center');assert.equal(c.headAlign,'center');}}
  assert.ok(geometry.actionDelta<1,JSON.stringify(geometry));
 }
 await page.setViewportSize({width:1366,height:950});
 const select=async(label,option)=>{await page.locator(label==='Sort'?'.st-key-auto_sort':'.st-key-auto_filter').getByRole('combobox').click();await page.getByRole('option',{name:option,exact:true}).click();};
 const first=await page.locator('.sc-auto-row a').first().innerText();await select('Sort','Oldest first');
 await page.waitForFunction(name=>document.querySelector('.sc-auto-row a')?.textContent!==name,first);
 await select('Trigger','Checkout abandoned');await page.waitForFunction(()=>document.querySelectorAll('.sc-auto-row').length===2);
 await select('Trigger','All triggers');await page.waitForFunction(()=>document.querySelectorAll('.sc-auto-row').length===3);
 await page.locator('[data-testid=stPopoverButton]:visible').first().click();await page.getByRole('button',{name:'Open editor',exact:true}).waitFor();await page.keyboard.press('Escape');
 await search.fill('');await search.press('Enter');
 const next=page.getByRole('button',{name:'Next',exact:true});await next.waitFor();await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent==='Next'&&!b.disabled));assert.equal(await next.isEnabled(),true);await next.click();
 await page.waitForFunction(()=>[...document.querySelectorAll('p')].some(p=>p.textContent.startsWith('Showing 13')));
 await page.getByRole('button',{name:'Previous',exact:true}).click();
 await page.waitForFunction(()=>[...document.querySelectorAll('p')].some(p=>p.textContent.startsWith('Showing 1–')));
 assert.equal(await page.getByTestId('stException').count(),0);
 await page.goto('http://127.0.0.1:8533');
 await search.fill('Overview metrics');await search.press('Enter');
 await page.locator('.sc-auto-row').filter({hasText:'Overview metrics counted fixture'}).getByText('2 (12.5%)',{exact:true}).waitFor();
 await page.locator('.st-key-auto-overview').screenshot({path:'tmp/overview-metrics-final.png'});
 console.log('PASS: persisted open count/rate, zero/no-send states, bounce rate, Revenue removal, shared grid geometry and centered actions at six widths, search/filter/sort/pagination/menu');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
