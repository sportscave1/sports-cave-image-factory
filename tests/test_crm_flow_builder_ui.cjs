// Local synthetic data only. Block all external browser requests.
const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
const page=await context.newPage();await page.setViewportSize({width:1440,height:1000});
await page.goto('http://127.0.0.1:8540/?fixture_checkout=1&fixture_run='+Date.now());
const dialog=page.getByRole('dialog');await dialog.getByRole('tab',{name:'Flow Builder',exact:true}).waitFor();
async function settings(index){const card=dialog.locator('[class*="st-key-flow-card-"]').nth(index);if(await card.locator('details').getAttribute('open')===null)await card.getByText('Step settings',{exact:true}).click();return card;}
assert.equal(await page.locator('.sc-auto-kpi').count(),0); // Overview unmounts while editing; its cache survives Back.
await dialog.getByRole('button',{name:'+ Add Email',exact:true}).click();
await dialog.getByRole('button',{name:'Edit email',exact:true}).nth(2).waitFor();
let menu=await settings(2);
await menu.getByRole('textbox',{name:'Email name',exact:true}).fill('Final follow-up');
await menu.getByRole('checkbox',{name:'Enable this email',exact:true}).press('Space');
await page.waitForFunction(()=>[...document.querySelectorAll('input[aria-label="Enable this email"]')].some(e=>!e.checked),{},{timeout:5000});
await menu.getByRole('button',{name:'Save step',exact:true}).click();
await dialog.getByText('Final follow-up',{exact:true}).waitFor({timeout:10000}).catch(async error=>{console.log(await dialog.innerText());await page.screenshot({path:'tmp/flow-settings-failure.png',fullPage:true});throw error;});
menu=await settings(2);await menu.getByRole('button',{name:'Move up',exact:true}).click();
await page.waitForFunction(()=>Array.from(document.querySelectorAll('[class*="st-key-flow-card-"] strong')).map(e=>e.textContent).indexOf('Final follow-up')===1);
menu=await settings(1);await menu.getByRole('button',{name:'Duplicate',exact:true}).click();
await dialog.getByText('Final follow-up copy',{exact:true}).waitFor();
menu=await settings(2);
await menu.getByRole('checkbox',{name:'Confirm delete email from this draft',exact:true}).press('Space');
await page.waitForFunction(()=>[...document.querySelectorAll('input[aria-label="Confirm delete email from this draft"]')].some(e=>e.checked),{},{timeout:5000});
await menu.getByRole('button',{name:'Delete email',exact:true}).click();
await dialog.getByText('Final follow-up copy',{exact:true}).waitFor({state:'hidden',timeout:10000}).catch(async error=>{console.log(await dialog.innerText());throw error;});
await dialog.getByRole('tab',{name:'Triggers & Timing',exact:true}).click();
await dialog.getByRole('textbox',{name:'Flow name',exact:true}).fill('Recovery builder fixture');
await dialog.getByRole('button',{name:'Save timing and rules',exact:true}).click();
await dialog.locator('.automation-title strong').filter({hasText:'Recovery builder fixture'}).waitFor();
await dialog.getByRole('tab',{name:'Flow Builder',exact:true}).click();
await dialog.getByRole('button',{name:'Test Flow',exact:true}).click();
await dialog.getByText('Simulation only.',{exact:false}).waitFor();
await dialog.getByRole('button',{name:'Test Flow',exact:true}).click();
await dialog.getByText('Simulation only.',{exact:false}).waitFor({state:'hidden'});
await dialog.getByRole('button',{name:'Edit email',exact:true}).first().click();
await dialog.getByRole('button',{name:'Flow Builder',exact:true}).waitFor();
await dialog.getByRole('button',{name:'Flow Builder',exact:true}).click();
await dialog.getByRole('tab',{name:'Flow Builder',exact:true}).last().waitFor();
await dialog.getByRole('tab',{name:'Activity',exact:true}).last().click();
await dialog.getByText('Scheduler ·',{exact:false}).waitFor();
await dialog.getByRole('tab',{name:'Flow Builder',exact:true}).last().click();
await dialog.getByRole('button',{name:'+ Add Email',exact:true}).waitFor();
for(const width of [1440,750,390,320]){await page.setViewportSize({width,height:1000});await page.screenshot({path:`tmp/flow-builder-${width}.png`,fullPage:true});assert.equal(await page.getByTestId('stException').count(),0);}
await dialog.getByRole('button',{name:'← Automations',exact:true}).click();await dialog.waitFor({state:'hidden'});
assert.equal(await page.locator('.sc-auto-kpi').count(),6);
console.log('PASS: existing overview preserved; modal sequence, add, timing, shared composer, simulation, activity, close, four viewport sizes');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
