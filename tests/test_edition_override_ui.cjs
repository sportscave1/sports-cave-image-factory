// Synthetic fixture only. All DB and Shopify writes are replaced in the fixture.
const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100}});
 await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 await page.goto('http://127.0.0.1:8895');const canvas=page.getByTestId('data-grid-canvas');await canvas.waitFor();
 await page.locator('.dvn-scroller').dblclick({position:{x:550,y:52}});
 const cell=page.locator('.gdg-input');await cell.waitFor();await cell.fill('5');await page.keyboard.press('Enter');
 await page.getByText(/1 unsaved change/).waitFor();
 await page.getByRole('button',{name:'Save & Sync Shopify',exact:true}).click();
 const dialog=page.getByRole('dialog');await dialog.waitFor();
 await dialog.getByText('This number may already have been allocated. Continue with manual override?',{exact:true}).waitFor();
 await dialog.getByRole('button',{name:'Confirm Override',exact:true}).click();await dialog.waitFor({state:'hidden'});
 await page.getByRole('button',{name:'Profile snapshot',exact:true}).click();
 await page.waitForFunction(()=>JSON.parse(document.querySelector('#edition-profile').textContent).first_next===5);
 const profile=JSON.parse(await page.locator('#edition-profile').textContent());assert.equal(profile.saves,1);
 assert.equal(await page.getByTestId('stException').count(),0);
 console.log('PASS: explicit cell edit, duplicate confirmation, one save, persistent fixture cursor 005');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
