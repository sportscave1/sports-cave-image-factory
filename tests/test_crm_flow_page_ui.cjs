// Real browser, disposable SQL and blocked external network only.
const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const base=process.env.FLOW_URL||'http://127.0.0.1:8540/';
 await page.goto(base+'?fixture_checkout=1&fixture_run=flow'+Date.now());
 await page.getByRole('button',{name:'Edit Email',exact:true}).first().waitFor();
 assert.equal(await page.getByRole('dialog').count(),0);assert.equal(await page.locator('.sc-auto-kpi').count(),0);
 assert.equal(await page.getByRole('tab',{name:'Flow Builder',exact:true}).count(),0);
 await page.locator('.sc-flow-thumbnail').first().waitFor({timeout:15000});
 await page.waitForFunction(()=>document.querySelector('.sc-flow-thumbnail')?.shadowRoot?.querySelector('.email')?.textContent.length>5);
 await page.screenshot({path:'tmp/unified-flow-desktop.png',fullPage:true});
 const rows=page.locator('[class*="st-key-flow-row-"]');assert.equal(await rows.count(),2);
 async function menu(i){await rows.nth(i).getByRole('button',{name:'⋮',exact:true}).click();return page.getByTestId('stPopoverBody');}
 let pop=await menu(0);await pop.getByRole('textbox',{name:'Email name',exact:true}).fill('First reminder');await pop.getByRole('spinbutton',{name:'Delay',exact:true}).fill('31');await pop.getByRole('button',{name:'Save step',exact:true}).click();
 await page.getByText('Email 1 · First reminder',{exact:true}).waitFor();await page.getByText('31 minutes after trigger · Enabled',{exact:true}).waitFor();
 await page.getByRole('button',{name:'+ Add Email',exact:true}).click();await rows.nth(2).waitFor();
 pop=await menu(2);await pop.getByRole('button',{name:'Move up',exact:true}).click();await page.getByTestId('stPopoverBody').waitFor({state:'hidden'});
 pop=await menu(1);await pop.getByRole('button',{name:'Duplicate',exact:true}).click();await rows.nth(3).waitFor();
 pop=await menu(2);await pop.getByRole('checkbox',{name:'Enable this email',exact:true}).press('Space');await pop.getByRole('button',{name:'Save step',exact:true}).click();await page.getByText(/Disabled/).first().waitFor();
 pop=await menu(2);await pop.getByRole('checkbox',{name:'Confirm delete email from this draft',exact:true}).press('Space');await page.waitForFunction(()=>[...document.querySelectorAll('input[aria-label="Confirm delete email from this draft"]')].some(e=>e.checked));await pop.getByRole('button',{name:'Delete email',exact:true}).click();await page.waitForFunction(()=>document.querySelectorAll('[class*="st-key-flow-row-"]').length===3);
 const previousThumbnail=await rows.first().locator('.sc-flow-thumbnail').getAttribute('id');
 await rows.first().getByRole('button',{name:'Edit Email',exact:true}).click();await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();
 await page.getByRole('textbox',{name:'Subject',exact:true}).fill('Updated subject for first email');await page.getByRole('textbox',{name:'Subject',exact:true}).press('Tab');
 await page.getByRole('button',{name:'Flow',exact:true}).click();await page.getByText('Updated subject for first email',{exact:true}).waitFor();
 await page.locator('.sc-flow-thumbnail').first().waitFor();assert.notEqual(await rows.first().locator('.sc-flow-thumbnail').getAttribute('id'),previousThumbnail);await page.locator('.sc-flow-thumbnail').first().click();await page.getByText('Saved email preview · neutral sample data',{exact:true}).waitFor();await page.getByRole('button',{name:'Close preview',exact:true}).click();
 for(const width of [1000,750,390,320]){await page.setViewportSize({width,height:1000});await page.locator('.st-key-automation-toolbar').scrollIntoViewIfNeeded();await page.screenshot({path:`tmp/unified-flow-${width}.png`,fullPage:true});assert.equal(await page.locator('.st-key-automation-toolbar').evaluate(e=>e.scrollWidth>e.clientWidth+2),false);assert.equal(await page.getByTestId('stMain').evaluate(e=>e.scrollWidth>e.clientWidth+2),false);}
 await page.setViewportSize({width:1440,height:1000});await page.getByRole('button',{name:'← Automations',exact:true}).click();await page.locator('.sc-auto-kpi').first().waitFor();
 await page.locator('[class*="st-key-auto_actions_"] button[data-testid="stPopoverButton"]:visible').first().click();
 assert.equal(await page.getByRole('button',{name:'Analytics',exact:true}).count(),0);
 await page.getByRole('button',{name:'Flow',exact:true}).click();await page.getByRole('button',{name:'Edit Email',exact:true}).first().waitFor();
 assert.equal(await page.getByRole('dialog').count(),0);assert.equal(await page.getByTestId('stException').count(),0);assert.deepEqual(errors,[]);
 await page.goto(base+'?fixture_checkout=1&fixture_steps=12&fixture_run=many'+Date.now());
 await page.waitForFunction(()=>document.querySelectorAll('[class*="st-key-flow-row-"]').length===12);
 await page.locator('.sc-flow-thumbnail').first().waitFor();
 assert.ok(await page.locator('.sc-flow-thumbnail').count()<12,'Off-screen thumbnails stay deferred');
 assert.equal(await page.locator('iframe').count(),0,'No editor or iframe mounted for thumbnails');
 await rows.last().scrollIntoViewIfNeeded();await rows.last().locator('.sc-flow-thumbnail').waitFor();
 await page.getByRole('button',{name:'← Automations',exact:true}).click();await page.locator('.sc-auto-kpi').first().waitFor();
 await page.locator('.sc-auto-row a[href*="automation="]').first().click();await page.getByRole('button',{name:'Edit Email',exact:true}).first().waitFor();
 await page.reload();await page.getByRole('button',{name:'Edit Email',exact:true}).first().waitFor();
 assert.equal(await page.getByRole('dialog').count(),0);assert.deepEqual(errors,[]);
 console.log('PASS unified Flow, real lazy thumbnails, inline operations, shared editor, no modal, navigation and responsive layout');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
