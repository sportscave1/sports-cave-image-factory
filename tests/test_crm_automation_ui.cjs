// Loopback-only synthetic preview. External assets/provider requests are blocked.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const evidence=path.resolve(process.env.CODEX_AUTOMATION_EVIDENCE || 'test-results/automation-home');fs.mkdirSync(evidence,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext();
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();
  for(const [width,height] of [[1920,1080],[1366,768],[750,900],[390,844],[320,740]]){
   await page.setViewportSize({width,height});await page.goto('http://127.0.0.1:8533');
   await page.getByRole('button',{name:'+ Create automation',exact:true}).waitFor();
   await page.locator('.sc-auto-row').first().waitFor();
   assert.equal(await page.getByTestId('stException').count(),0);
   assert.equal(await page.locator('.sc-auto-kpi').count(),6);
   const geometry=await page.evaluate(()=>({width:innerWidth,body:document.documentElement.scrollWidth,
     rowOverflow:[...document.querySelectorAll('.sc-auto-row')].some(e=>e.scrollWidth>e.clientWidth+2)}));
   assert.ok(geometry.body<=width+2,JSON.stringify(geometry));
   assert.ok(!geometry.rowOverflow,JSON.stringify(geometry));
   assert.equal(await page.getByText('Shopify trigger diagnostic',{exact:true}).count(),0);
   await page.getByRole('button',{name:'Overview',exact:true}).waitFor();
   await page.getByRole('button',{name:'Recent Activity',exact:true}).waitFor();
   await page.screenshot({path:path.join(evidence,'automation-home-'+width+'.png'),fullPage:true});
   console.log('Automations Home '+width+'px: no overflow; six KPI cards; real fixture rows');
  }
  await page.setViewportSize({width:1366,height:768});
  const rowsBefore=await page.locator('.sc-auto-row').count();
  await page.locator('[class*=st-key-auto-row-]').filter({hasText:'Abandoned checkout · local fixture'}).first().getByTestId('stPopoverButton').first().click();
  await page.getByRole('button',{name:'Analytics',exact:true}).click();
  await page.getByRole('dialog').waitFor();
  await page.getByRole('heading',{name:'Abandoned checkouts',exact:true}).waitFor();
  assert.equal(await page.getByTestId('stException').count(),0);
  await page.getByRole('button',{name:'Close',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  await page.waitForTimeout(750);
  if(!await page.getByRole('button',{name:'Delete',exact:true}).isVisible())await page.locator('[class*=st-key-auto-row-]').filter({hasText:'Abandoned checkout · local fixture'}).first().getByTestId('stPopoverButton').first().click();
  await page.getByRole('button',{name:'Delete',exact:true}).click();
  await page.getByRole('dialog').waitFor();
  await page.getByRole('button',{name:'Cancel',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  assert.equal(await page.locator('.sc-auto-row').count(),rowsBefore);
  await page.getByRole('button',{name:'+ Create automation',exact:true}).click();
  await page.getByRole('dialog').waitFor();
  assert.ok(await page.getByRole('button',{name:'Welcome series · Customer subscribes to email',exact:true}).count());
  await page.getByRole('button',{name:'Welcome series · Customer subscribes to email',exact:true}).click();
  await page.getByRole('button',{name:'Publish now',exact:true}).waitFor();
  await page.getByText('Email Preview',{exact:true}).waitFor();
  assert.equal(await page.getByTestId('stException').count(),0);
  for(const name of ['Settings','Editor','Templates'])assert.ok(await page.getByRole('tab',{name,exact:true}).count());
  assert.equal(await page.getByText(/^Flow · \d+ emails$/).count(),0,'No main Flow accordion');
  assert.equal(await page.locator('.st-key-crm-composer-controls').getByText('Flow email',{exact:true}).count(),1,'Email selection belongs to left panel');
  assert.equal(await page.locator('.st-key-crm-composer-controls').getByRole('button',{name:'Duplicate email',exact:true}).count(),1);
  assert.equal(await page.getByText('Segment',{exact:true}).count(),0);
  for(const [width,height] of [[1920,1080],[1366,768],[750,900],[390,844],[320,740]]){
   await page.setViewportSize({width,height});
   await page.waitForTimeout(200);
   const geometry=await page.evaluate(()=>({width:innerWidth,body:document.documentElement.scrollWidth}));
   assert.ok(geometry.body<=width+2,JSON.stringify(geometry));
   assert.equal(await page.getByTestId('stException').count(),0);
   await page.screenshot({path:path.join(evidence,'automation-editor-'+width+'.png'),fullPage:true});
   console.log('Shared automation editor '+width+'px: no horizontal overflow');
  }
  await page.setViewportSize({width:1366,height:768});
  await page.getByRole('button',{name:'+ Add email · duplicate previous',exact:true}).click();
  await page.getByText('Email 2 · Untitled · 1440 min delay',{exact:true}).waitFor();
  await page.getByRole('button',{name:'+ Add email · start blank',exact:true}).click();
  await page.getByText('Email 3 · Untitled · 1440 min delay',{exact:true}).waitFor();
  const selector=page.locator('.st-key-crm-composer-controls [data-testid=stSelectbox]').filter({hasText:'Flow email'});
  await selector.locator('[role=combobox]').click();
  await page.getByRole('option',{name:'Email 1 · Untitled · 0 min delay',exact:true}).click();
  await selector.getByText('Email 1 · Untitled · 0 min delay',{exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('input[aria-label="Delay before email (minutes)"]')?.value==='0');
  await page.locator('.st-key-crm-composer-controls').getByRole('button',{name:'Duplicate email',exact:true}).click();
  await selector.getByText('Email 2 · Untitled · 0 min delay',{exact:true}).waitFor();
  assert.equal(await page.getByText(/^Flow · \d+ emails$/).count(),0);
  assert.equal(await page.getByTestId('stException').count(),0);
  console.log('Add email: duplicate and blank steps; same shared composer; Cancel delete retains row');
  console.log('Shared composer: Settings / Editor / Templates; no Segment; preview; Publish now');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
