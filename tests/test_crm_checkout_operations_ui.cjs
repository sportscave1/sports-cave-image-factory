// Mock-only operational page; deny every non-loopback browser request.
const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:process.env.TEST_BROWSER||'chrome',headless:true});try{
 const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage();await page.setViewportSize({width:1366,height:900});await page.goto('http://127.0.0.1:8538');
 const add=page.getByRole('button',{name:'Add to flow',exact:true});await add.waitFor();assert.equal(await add.isDisabled(),true);
 const table=page.frameLocator('iframe[title="crm_automation_analytics_ui.crm_checkout_table"]');
 await table.getByText('Joanne Lawrence').waitFor();
 assert.deepEqual(await table.locator('th').allTextContents(),['','Customer','Created','Email 1','Email 2','Email 3','Email 4','Email 5']);
 assert.ok(await table.locator('tbody tr').first().evaluate(el=>el.getBoundingClientRect().height)<=42);
 assert.equal(await page.getByText('All',{exact:true}).count(),0);
 assert.equal(await page.locator('[role=dialog]>div').first().evaluate(el=>getComputedStyle(el).paddingTop),'12px');
 assert.ok((await page.getByRole('textbox',{name:'Search and filter'}).boundingBox()).height<=34);
 await table.getByText('Sent ✓',{exact:true}).waitFor();
 assert.equal(await table.locator('.green').filter({hasText:'Sent ✓'}).count(),1);
 await table.getByRole('checkbox',{name:'Select Joanne Lawrence',exact:true}).check();await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent==='Add to flow'&&!b.disabled));
 await table.getByRole('checkbox',{name:'Select Guest Collector',exact:true}).check();
 const clicked=Date.now();await add.click();await table.locator('.enrollment-progress').getByText('Queued',{exact:true}).first().waitFor();assert.ok(Date.now()-clicked<1500);
 await table.getByText('Checking eligibility\u2026',{exact:true}).first().waitFor();
 await table.getByText('Sent ✓',{exact:true}).first().waitFor();
 await table.locator('tbody tr').filter({hasText:'Joanne Lawrence'}).getByText(/23h 59m|1d 0h/).waitFor();
 await page.getByText('1 enrolled; 1 sent; 0 queued; 1 skipped; 0 failed.',{exact:true}).waitFor();
 await add.click();await table.getByText('Already in flow',{exact:true}).first().waitFor({timeout:12000}).catch(async error=>{console.log(await table.locator('tbody').innerText());throw error;});
 await table.getByRole('button',{name:'Details Joanne Lawrence'}).click();await page.getByText('Checkout details \u00b7 #100',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Close details'}).click();await page.getByText('Checkout details \u00b7 #100',{exact:true}).waitFor({state:'hidden'});
 const search=page.getByRole('textbox',{name:'Search and filter'});await search.fill('fixture1@example.test');await search.press('Enter');await table.getByText('Brian Albers').waitFor();await table.getByText('Joanne Lawrence').waitFor({state:'hidden'});
 assert.equal(await table.getByText('Joanne Lawrence').count(),0);assert.equal(await add.isDisabled(),true);
 await search.fill('');await search.press('Enter');await table.getByText('Joanne Lawrence').waitFor();
 await table.getByRole('checkbox',{name:'Select visible checkouts',exact:true}).check();
 await add.click();await table.locator('.enrollment-progress').getByText('Queued',{exact:true}).first().waitFor();
 // Search remains interactive while independent worker rows are pending.
 await search.fill('fixture3@example.test');await search.press('Enter');await table.getByText('Fixture 3',{exact:true}).waitFor();
 await search.fill('');await search.press('Enter');
 const row7=table.locator('tbody tr').filter({hasText:'Fixture 7'});
 await row7.getByText('Sent ✓',{exact:true}).waitFor();
 await table.locator('tbody tr').filter({hasText:'Fixture 3'}).getByText('Checking eligibility\u2026',{exact:true}).waitFor();
 await table.locator('tbody tr').filter({hasText:'Fixture 5'}).getByText('Suppressed',{exact:true}).first().waitFor();
 await table.getByRole('button',{name:'Retry Fixture 4',exact:true}).waitFor();
 await table.getByRole('button',{name:'Retry Fixture 4',exact:true}).click();
 await table.locator('tbody tr').filter({hasText:'Fixture 4'}).getByText('Sent ✓',{exact:true}).waitFor();
 await table.locator('tbody tr').filter({hasText:'Fixture 3'}).getByText('Sent ✓',{exact:true}).waitFor();
 await page.screenshot({path:'docs/checkout-flow-evidence/operations-desktop.png',fullPage:true});
 for(const width of [750,390,320]){await page.setViewportSize({width,height:900});await page.waitForTimeout(700);await page.screenshot({path:`docs/checkout-flow-evidence/operations-${width}.png`,fullPage:true});assert.equal(await page.getByTestId('stException').count(),0);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(await table.locator('body').evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
 for(const text of ['Recent activity','No accepted sends in this reporting period.','Not in flow \u00b7 Add to flow','Revenue \u00b7 \u2014'])assert.equal(await page.getByText(text,{exact:true}).count(),0);
 console.log('PASS: columns, per-email states, selection bridge, disabled action, enrolment results, idempotence, details, email search, four viewport sizes, 12-row asynchronous progress, slow-row isolation, mixed outcomes, row retry, responsive search, no analytics clutter');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
