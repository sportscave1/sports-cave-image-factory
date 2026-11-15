// Real Refresh -> real Posting render, fake Dropbox/metadata, no Meta writes.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 for(const width of [1440,390]){
  const context=await browser.newContext({viewport:{width,height:1000}});
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();page.setDefaultTimeout(20000);
  await page.goto('http://127.0.0.1:8557/?format=Carousel&count=4&draft=1&posting=1');
  const headline=page.getByRole('textbox',{name:'Card 1 headline',exact:true});await headline.waitFor();
  await headline.fill('Saved four-card draft');await headline.press('Tab');
  const save=page.locator('[class*="st-key-ads-images-save-open"] button');
  await save.waitFor().catch(async error=>{console.log((await page.locator('body').innerText()).slice(-9000));await page.screenshot({path:'tmp/refresh-draft-error.png',fullPage:true});throw error;});await save.click();
  await page.getByRole('button',{name:'Save setup notes here',exact:true}).click();
  const post=page.getByRole('button',{name:'POST NOW',exact:true});await post.waitFor();
  assert.equal(await headline.inputValue(),'Saved four-card draft');
  assert.equal(await page.getByText('Card execution notes (JSON)',{exact:true}).count(),0);
  await post.click();await page.getByRole('heading',{name:'Post Ad',exact:true}).waitFor();
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('input')).some(e=>e.value==='Saved four-card draft')).catch(async error=>{console.log((await page.locator('body').innerText()).slice(-14000));await page.screenshot({path:'tmp/refresh-draft-error.png',fullPage:true});throw error;});
  assert.equal(await page.getByRole('textbox',{name:'Card Headline 1',exact:true}).inputValue(),'Saved four-card draft');
  assert.equal(await page.getByRole('textbox',{name:'Card Headline 5',exact:true}).count(),0);
  assert.equal(await page.getByRole('button',{name:'Create Ad',exact:true}).isDisabled(),true);
  await page.getByRole('button',{name:'Refresh Meta',exact:true}).click();
  assert.equal(await page.getByRole('textbox',{name:'Card Headline 1',exact:true}).inputValue(),'Saved four-card draft');
  await page.getByRole('button',{name:'Return to Creative Refresh fixture',exact:true}).click();
  await headline.waitFor();assert.equal(await headline.inputValue(),'Saved four-card draft');
  assert.equal(await page.getByTestId('stException').count(),0);
  await page.screenshot({path:`tmp/refresh-draft-${width}.png`,fullPage:true});await context.close();
 }
 console.log('PASS desktop/narrow four-card draft save, real Posting handoff, missing-media guard, refresh and return');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
