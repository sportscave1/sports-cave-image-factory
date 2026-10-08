// Loopback-only context-menu interaction and responsive contract.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext();
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();
  for(const width of [1920,1366,750,390,320]){
   await page.setViewportSize({width,height:900});await page.goto('http://127.0.0.1:8533');
   await page.locator('.sc-auto-row').first().waitFor();
   const trigger=page.locator('[data-testid=stPopoverButton]:visible').first();
   await trigger.click();
   const menu=page.getByTestId('stPopoverBody');await menu.waitFor();
   const metrics=await menu.evaluate(e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width,height:r.height,viewport:innerWidth};});
   assert.ok(metrics.width<=200&&metrics.height<=210,JSON.stringify(metrics));
   assert.ok(metrics.left>=0&&metrics.right<=width,JSON.stringify(metrics));
   assert.equal(await menu.locator('button:visible').count(),4);
   const textLeft=await menu.locator('button:visible p').evaluateAll(items=>items.map(e=>e.getBoundingClientRect().left));
   assert.ok(Math.max(...textLeft)-Math.min(...textLeft)<2,'Aligned action labels');
   const analytics=menu.getByRole('button',{name:'Flow',exact:true});
   await analytics.focus();await page.keyboard.press('ArrowDown');
   assert.equal(await menu.getByRole('button',{name:'Duplicate',exact:true}).evaluate(e=>e===document.activeElement),true);
   await page.keyboard.press('Home');assert.equal(await analytics.evaluate(e=>e===document.activeElement),true);
   await page.keyboard.press('End');
   assert.equal(await menu.locator('button:not(:disabled)').last().evaluate(e=>e===document.activeElement),true);
   await page.keyboard.press('ArrowDown');assert.equal(await analytics.evaluate(e=>e===document.activeElement),true);
   await page.keyboard.press('Escape');await menu.waitFor({state:'hidden'});
   await trigger.click();await menu.waitFor();
   await page.getByRole('heading',{name:'Automations',exact:true}).click();await menu.waitFor({state:'hidden'});
   await trigger.focus();await page.keyboard.press('Enter');await menu.waitFor();
   await page.keyboard.press('Escape');await menu.waitFor({state:'hidden'});
   await trigger.focus();await page.keyboard.press('Space');await menu.waitFor();
   await page.keyboard.press('Escape');await menu.waitFor({state:'hidden'});
   assert.equal(await page.getByTestId('stException').count(),0);
   console.log(`Context menu ${width}px: compact, in viewport; arrows/Home/End/Escape/outside click/Enter/Space pass`);
  }
  // Existing Analytics dispatch still opens its full dialog and dismisses menu.
  await page.setViewportSize({width:1366,height:768});
  await page.locator('[data-testid=stPopoverButton]:visible').first().click();
  await page.getByRole('button',{name:'Flow',exact:true}).click();
  await page.getByRole('dialog').waitFor();await page.getByTestId('stPopoverBody').waitFor({state:'hidden'});
  await page.getByRole('button',{name:'Close',exact:true}).click();
  console.log('Analytics handler opens dialog; action menu closes');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
