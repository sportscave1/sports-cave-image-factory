// Loopback synthetic checkouts only. No transport or worker is run.
const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();
  for(const width of [1920,1366,750,390,320]){
   await page.setViewportSize({width,height:950});await page.goto('http://127.0.0.1:8533/?fixture_analytics=1');
   await page.getByRole('textbox',{name:'Search automations',exact:true}).fill('Abandoned checkout · local fixture');
   await page.getByRole('textbox',{name:'Search automations',exact:true}).press('Tab');
   const row=page.locator('[class*=st-key-auto-row-]').filter({hasText:'Abandoned checkout · local fixture'}).first();await row.waitFor();
   await row.locator('[data-testid=stPopoverButton]:visible').click();const start=Date.now();await page.getByRole('button',{name:'Analytics',exact:true}).click();
   const dialog=page.getByRole('dialog');await dialog.getByRole('heading',{name:'Automation analytics',exact:true}).waitFor();
   const shell=Date.now()-start;
   try{await dialog.getByText(/matching checkouts ·/).waitFor();}catch(e){console.log((await dialog.innerText()).slice(0,3500));throw e;}
   const table=Date.now()-start;
   assert.equal(await page.getByTestId('stException').count(),0);
   for(const old of ['Next checkout page','Newest checkouts'])assert.equal(await dialog.getByRole('button',{name:old,exact:true}).count(),0);
   const geometry=await dialog.evaluate(e=>({width:e.clientWidth,scroll:e.scrollWidth}));assert.ok(geometry.scroll<=geometry.width+2,JSON.stringify(geometry));
   console.log(`Analytics ${width}px: shell ${shell}ms; canonical table ${table}ms; no dialog overflow`);
   assert.ok(table<2500,'Local table exceeded 2.5s including command/navigation');
   await page.getByRole('button',{name:'Close',exact:true}).click();
  }
  await page.setViewportSize({width:1366,height:950});
  const row=page.locator('[class*=st-key-auto-row-]').filter({hasText:'Abandoned checkout · local fixture'}).first();
  await row.locator('[data-testid=stPopoverButton]:visible').click();let start=Date.now();await page.getByRole('button',{name:'Analytics',exact:true}).click();
  const dialog=page.getByRole('dialog');await dialog.getByText(/matching checkouts ·/).waitFor();console.log('Warm cached reopen '+(Date.now()-start)+'ms');
  const range=dialog.getByTestId('stSelectbox');
  for(const period of ['Last 7 days','Last 90 days','Last year','All time','Last 30 days']){
   await range.locator('[role=combobox]').click();await page.getByRole('option',{name:period,exact:true}).click({force:true});
   await dialog.getByText(/matching checkouts ·/).waitFor();assert.equal(await page.getByTestId('stException').count(),0);
   if(period==='All time'){
    await page.waitForFunction(()=>[...document.querySelectorAll('[role=dialog] p')].some(e=>parseInt(e.textContent)>=5000&&e.textContent.includes('matching checkouts')));
    const grid=dialog.getByTestId('stDataFrame').locator('.dvn-scroller');await grid.hover();const startScroll=Date.now();await page.mouse.wheel(0,12000);await page.waitForTimeout(100);
    console.log('All-time 5000+ rows use virtualized canvas; scroll input '+(Date.now()-startScroll)+'ms');
   }
  }
  await dialog.getByRole('textbox',{name:'Search checkouts',exact:true}).fill('local0@example.test');
  await dialog.getByRole('textbox',{name:'Search checkouts',exact:true}).press('Tab');
  await dialog.getByText('1 matching checkouts · 0 recovered',{exact:true}).waitFor();
  const grid=dialog.getByTestId('stDataFrame');await grid.locator('.dvn-scroller').click({position:{x:15,y:50}});
  const add=dialog.getByRole('button',{name:'Add to flow',exact:true});await add.waitFor();assert.equal(await add.isEnabled(),true);
  assert.equal(await dialog.getByRole('checkbox').count(),0);
  start=Date.now();await add.click();await dialog.getByText('Already in flow',{exact:true}).waitFor();
  assert.equal(await add.isEnabled(),false);assert.ok(await dialog.getByText(/In Flow — Email 1 pending/).count());
  console.log('Selected historical checkout → durable journey in '+(Date.now()-start)+'ms; immediate pending state; no inline mail');
  assert.equal(await page.getByTestId('stException').count(),0);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
