// Synthetic loopback DB only. No emails, provider requests or real publication.
const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const start=Date.now();await page.goto('http://127.0.0.1:8533/?fixture_analytics=1&fixture_stability=1');
  const row=()=>page.locator('[class*=st-key-auto-row-]').filter({hasText:'Abandoned checkout · local fixture'}).first();
  await row().waitFor();console.log('Cold useful row ms',Date.now()-start);
  async function sample(label){await page.getByRole('button',{name:'Fixture sample metrics',exact:true}).click();await page.waitForTimeout(150);const data=JSON.parse(await page.locator('#fixture-measurements').innerText());console.log(label,JSON.stringify(data));return data;}
  await page.waitForFunction(()=>document.querySelectorAll('.sc-auto-kpis .sc-home-unresolved').length===0);
  let before;for(let n=0;n<15;n++){await page.waitForTimeout(500);before=await sample('warming');if(before.pending===0)break;}assert.equal(before.pending,0);console.log('initial',JSON.stringify(before));
  await page.waitForTimeout(60000);
  const idle=await sample('idle60');assert.ok(idle.queries-before.queries<=3,'Idle DB query storm');
  assert.equal(idle.provider_calls,0);assert.equal(idle.pending,0);
  for(let i=1;i<=50;i++){
   await row().locator('[data-testid=stPopoverButton]:visible').click();await page.getByRole('button',{name:'Analytics',exact:true}).click();
   const dialog=page.getByRole('dialog');await dialog.getByRole('heading',{name:'Automation analytics',exact:true}).waitFor();
   if(i===1){await dialog.getByText('Last 30 days',{exact:true}).click();await page.getByRole('option',{name:'All time',exact:true}).click({force:true});}
   await dialog.getByText(/matching checkouts/).waitFor();assert.equal(await dialog.getByText('This Automations section is temporarily unavailable. Navigation remains available.',{exact:true}).count(),0);await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});
   await row().locator('[data-testid=stPopoverButton]:visible').click();await page.getByRole('button',{name:'Open editor',exact:true}).click();
   await page.getByRole('button',{name:'← Automations',exact:true}).waitFor();await page.getByRole('button',{name:'← Automations',exact:true}).click();await row().waitFor();await page.waitForTimeout(200);
   assert.equal(await page.getByTestId('stException').count(),0);assert.equal(await page.getByText('This Automations section is temporarily unavailable. Navigation remains available.',{exact:true}).count(),0);
   if([10,25,50].includes(i))await sample('cycle'+i);
  }
  for(let i=0;i<100;i++){
   await page.getByRole('button',{name:'Fixture leave Automations',exact:true}).click();await page.getByRole('heading',{name:'Lightweight fixture page',exact:true}).waitFor();
   await page.getByRole('button',{name:'Fixture return Automations',exact:true}).click();await row().waitFor();await page.waitForTimeout(200);
  }
  const final=await sample('after100navigation');assert.ok(final.futures<=16);assert.ok(final.threads<=before.threads+3);assert.ok(final.provider_calls<=50,'More than one checkout lookup per explicit editor opening');
  assert.deepEqual(errors,[]);console.log('50 workflow cycles + 100 navigation pairs: PASS');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
