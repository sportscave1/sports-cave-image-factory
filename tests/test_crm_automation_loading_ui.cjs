// Full Streamlit + real local SQL; never contacts production or a mail provider.
const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});let assertions=0;
 try {
  for(const width of [1920,1366,750,390,320]) {
   const context=await browser.newContext({viewport:{width,height:950}});
   await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
   const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
   for(const status of ['Empty','Draft','Publishing','Live','Failed']) {
    const start=Date.now();await page.goto('http://127.0.0.1:8534/?case='+status);
    await page.getByRole('heading',{name:'Automations',exact:true}).waitFor();
    if(status!=='Empty')await page.locator('.sc-auto-name').filter({hasText:'Reminder 1'}).waitFor();
    await page.waitForFunction(()=>!document.querySelector('.sc-home-unresolved')&&!document.body.innerText.includes('Loading recent activity…'),{},{timeout:25000});
    assert.equal(await page.getByText('Loading automations…',{exact:true}).count(),0);assertions++;
    assert.equal(await page.getByTestId('stException').count(),0);assertions++;
    if(status!=='Empty') {
     const expected={Draft:'Draft',Publishing:'Publishing…',Live:'Live',Failed:'Publish failed'}[status];
     await page.locator('.sc-auto-pill').filter({hasText:expected}).waitFor();assertions++;
    }
    await page.reload();await page.waitForFunction(()=>!document.querySelector('.sc-home-unresolved')&&!document.body.innerText.includes('Loading recent activity…'),{},{timeout:25000});
    await page.getByText('Fixture remains interactive',{exact:true}).waitFor();assertions++;
    console.log(width,status,'cold/reload settled ms',Date.now()-start);
   }
   await page.goto('http://127.0.0.1:8534/?case=Empty');
   await page.getByRole('button',{name:'Fixture publish first automation',exact:true}).click();
   await page.locator('.sc-auto-pill').filter({hasText:'Publishing…'}).waitFor();assertions++;
   await page.getByRole('button',{name:'Fixture complete publication',exact:true}).click();
   await page.locator('.sc-auto-pill').filter({hasText:'Live'}).waitFor({timeout:15000});assertions++;
   await page.getByRole('button',{name:'Fixture publish first automation',exact:true}).click();
   await page.locator('.sc-auto-pill').filter({hasText:'Publishing…'}).waitFor();
   await page.getByRole('button',{name:'Fixture fail publication',exact:true}).click();
   await page.locator('.sc-auto-pill').filter({hasText:'Publish failed'}).waitFor({timeout:15000});assertions++;
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);assert.equal(overflow,false);assertions++;
   for(const failure of ['counts','activity','metrics']) {
    await page.goto('http://127.0.0.1:8534/?case=Live&failure='+failure);
    await page.locator('.sc-auto-name').filter({hasText:'Reminder 1'}).waitFor();
    await page.waitForFunction(()=>!document.querySelector('.sc-home-unresolved')&&!document.body.innerText.includes('Loading recent activity…'),{},{timeout:25000});
    assert.equal(await page.getByTestId('stException').count(),0);assertions++;
    assert.equal(await page.getByText('Synthetic private diagnostic',{exact:true}).count(),0);assertions++;
    await page.getByRole('button',{name:'Retry',exact:true}).waitFor();assertions++;
   }
   assert.deepEqual(errors,[]);assertions++;await context.close();
  }
 }finally{await browser.close()}
 console.log('Automations cold-state/reload/publication browser assertions:',assertions);
})().catch(e=>{console.error(e);process.exit(1)});
