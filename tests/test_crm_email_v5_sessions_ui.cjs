// Concurrent sessions retain independent unsent test addresses. Never submits.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 await Promise.all([0,1].map(async index=>{
  const context=await browser.newContext({viewport:{width:index?390:1440,height:1000}});
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();page.setDefaultTimeout(20000);
  await page.goto('http://127.0.0.1:8543/');await page.locator('.sc-home-row').first().waitFor();
  await page.locator('.st-key-crm-home-table [data-testid=stPopoverButton]').first().click();
  await page.getByRole('button',{name:'Edit',exact:true}).click();await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();
  await page.getByRole('button',{name:'Send test',exact:true}).click();
  const field=page.getByRole('textbox',{name:'Send test email',exact:true}),value='session'+index+'@example.test';
  await field.fill(value);await field.press('Tab');await page.keyboard.press('Escape');
  await field.waitFor({state:'hidden'});
  await page.getByRole('button',{name:'Send test',exact:true}).click();await field.waitFor();
  assert.equal(await field.inputValue(),value);assert.equal(await page.getByTestId('stException').count(),0);
  await context.close();
 }));console.log('PASS concurrent desktop/narrow unsent address isolation and reopen');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
