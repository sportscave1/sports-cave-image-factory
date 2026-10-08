// Real Streamlit fragment + production cache; no database/provider connections.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const context=await browser.newContext({viewport:{width:1366,height:900}});await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage();await page.goto('http://127.0.0.1:8539');
 await page.getByText('Abandoned checkouts',{exact:true}).click();
 const frame=page.frameLocator('iframe[title="crm_automation_analytics_ui.crm_checkout_table"]');
 await frame.getByRole('button',{name:'Details Customer A 0',exact:true}).waitFor();
 assert.equal(await frame.locator('tbody tr').count(),50);
 const first=frame.locator('tbody tr').first(),clock=first.locator('td').nth(3);
 assert.match(await clock.textContent(),/m \d+s/);
 const fullRuns=await page.getByText(/Full page runs:/).textContent();
 const initial=await clock.textContent();await page.waitForTimeout(2200);assert.notEqual(await clock.textContent(),initial);
 assert.equal(await page.getByText(/Full page runs:/).textContent(),fullRuns);
 // Unsaved typing remains intact across the status-only fragment refresh.
 const search=page.getByRole('textbox',{name:'Search and filter'});await search.fill('still typing');
 await first.getByText('Sent ✓',{exact:true}).waitFor({timeout:22000});
 assert.equal(await search.inputValue(),'still typing');
 assert.equal(await page.getByText(/Full page runs:/).textContent(),fullRuns);
 await search.fill('fixture11@example.test');await search.press('Enter');await frame.getByRole('button',{name:'Details Customer A 0',exact:true}).waitFor({state:'hidden'});await frame.getByRole('button',{name:'Details Customer L 11',exact:true}).waitFor();assert.equal(await frame.locator('tbody tr').count(),1);
 await search.fill('');await search.press('Enter');await frame.getByRole('button',{name:'Details Customer A 0',exact:true}).waitFor();
 await frame.getByRole('checkbox',{name:'Select Customer A 0',exact:true}).check();
 await page.getByRole('button',{name:'Next checkouts',exact:true}).click();await frame.getByRole('button',{name:'Details Customer Y 50',exact:true}).waitFor();
 await page.getByRole('button',{name:'Previous checkouts',exact:true}).click();await frame.getByRole('button',{name:'Details Customer A 0',exact:true}).waitFor();
 assert.equal(await frame.getByRole('checkbox',{name:'Select Customer A 0',exact:true}).isChecked(),true);
 assert.equal(await page.getByTestId('stException').count(),0);
 console.log('PASS persisted status refresh through real fragment/cache, local ticking, no full page rerun, unsubmitted search preservation, server pagination and selections');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
