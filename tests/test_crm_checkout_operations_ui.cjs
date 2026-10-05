// Mock-only operational page; deny every non-loopback browser request.
const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage();await page.setViewportSize({width:1366,height:900});await page.goto('http://127.0.0.1:8538');
 const add=page.getByRole('button',{name:'Add to flow',exact:true});await add.waitFor();assert.equal(await add.isDisabled(),true);
 const table=page.frameLocator('iframe[title="crm_automation_analytics_ui.crm_checkout_table"]');
 await table.getByText('Joanne Lawrence').waitFor();
 assert.deepEqual(await table.locator('th').allTextContents(),['','Checkout','Created','Customer name','Region','Recovery status','Time to send']);
 assert.ok(await table.locator('tbody tr').first().evaluate(el=>el.getBoundingClientRect().height)<=42);
 assert.equal(await page.getByText('All',{exact:true}).count(),0);
 assert.equal(await page.locator('[role=dialog]>div').first().evaluate(el=>getComputedStyle(el).paddingTop),'12px');
 assert.ok((await page.getByRole('textbox',{name:'Search and filter'}).boundingBox()).height<=34);
 await table.getByText('Sent',{exact:true}).waitFor();
 for(const [text,cls] of [['Not sent','red'],['Not recovered','orange'],['Recovered','green']])assert.equal(await table.locator('.pill.'+cls).filter({hasText:text}).count(),1);
 await table.getByRole('checkbox',{name:'Select #100',exact:true}).check();await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent==='Add to flow'&&!b.disabled));
 await table.getByRole('checkbox',{name:'Select #102',exact:true}).check();
 await add.click();await page.getByText('Added to flow',{exact:true}).waitFor({state:'attached'});
 await table.getByText('1h 18m remaining',{exact:true}).waitFor();
 await add.click();await page.getByText('Already in flow',{exact:true}).waitFor({state:'attached'});
 await table.getByRole('button',{name:'Details #100'}).click();await page.getByText('Checkout details \u00b7 #100',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Close details'}).click();await page.getByText('Checkout details \u00b7 #100',{exact:true}).waitFor({state:'hidden'});
 const search=page.getByRole('textbox',{name:'Search and filter'});await search.fill('fixture1@example.test');await search.press('Enter');await table.getByText('Brian Albers').waitFor();await table.getByText('Joanne Lawrence').waitFor({state:'hidden'});
 assert.equal(await table.getByText('Joanne Lawrence').count(),0);assert.equal(await add.isDisabled(),true);
 await search.fill('');await search.press('Enter');await table.getByText('Joanne Lawrence').waitFor();
 await page.screenshot({path:'tmp/checkout-operations-desktop.png',fullPage:true});
 for(const width of [750,390,320]){await page.setViewportSize({width,height:900});await page.screenshot({path:`tmp/checkout-operations-${width}.png`,fullPage:true});assert.equal(await page.getByTestId('stException').count(),0);}
 for(const text of ['Recent activity','No accepted sends in this reporting period.','Not in flow \u00b7 Add to flow','Revenue \u00b7 \u2014'])assert.equal(await page.getByText(text,{exact:true}).count(),0);
 console.log('PASS: columns, status pills, selection bridge, disabled action, enrolment results, idempotence, details, email search, four viewport sizes, no analytics clutter');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
