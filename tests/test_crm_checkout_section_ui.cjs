// Synthetic fixture only; external requests are blocked.
const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage();await page.setViewportSize({width:1440,height:1000});
 await page.goto('http://127.0.0.1:8540/?fixture_checkout=1&fixture_run=template'+Date.now());
 await page.getByRole('button',{name:'Edit email',exact:true}).first().click();
 await page.getByRole('tab',{name:'Templates',exact:true}).click();
 await page.getByText('Default Abandoned Checkout',{exact:true}).waitFor();
 assert.equal(await page.getByText('Abandoned Checkout — Collector Reminder',{exact:true}).count(),0);
 await page.locator('.st-key-edit_email_default_checkout button').click();
 await page.getByRole('textbox',{name:'Master template HTML / CSS',exact:true}).waitFor();
 assert.equal(await page.getByTestId('stException').count(),0);
 await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await page.getByRole('tab',{name:'Editor',exact:true}).click();
 const frame=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]');
 await frame.getByText('Add section',{exact:false}).click();
 await frame.locator('[data-add="checkout"]').click();
 await frame.getByRole('button',{name:'Edit Abandoned Checkout',exact:true}).waitFor();
 const source=frame.getByRole('textbox',{name:'Abandoned Checkout HTML',exact:true});
 if(!await source.count())await frame.getByRole('button',{name:'Edit Abandoned Checkout',exact:true}).click();
 await source.waitFor();assert.match(await source.inputValue(),/SC_ABANDONED_CHECKOUT/);
 await source.fill((await source.inputValue()).replace('Still thinking it over?','Editable browser draft'));
 await source.press('Tab');
 await page.waitForFunction(()=>[...document.querySelectorAll('iframe')].some(f=>f.srcdoc.includes('Editable browser draft')));
 await page.screenshot({path:'tmp/checkout-editable-desktop.png',fullPage:true});
 assert.equal(await page.getByTestId('stException').count(),0);
 console.log('PASS: compact defaults, master editor, checkout insertion and live HTML preview');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
