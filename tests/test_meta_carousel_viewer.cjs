// Synthetic loopback fixture only; no provider requests or mutations.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext();
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();
  for(const width of [1366,750,390,320]){
   await page.setViewportSize({width,height:768});
   await page.goto('http://127.0.0.1:8532');
   await page.getByText('CARD 1 OF 6',{exact:true}).waitFor();
   for(let i=1;i<=6;i++){
    await page.getByText(`CARD ${i} OF 6`,{exact:true}).waitFor();
    await page.getByText(`Headline: Headline ${i}`,{exact:true}).waitFor();
    const bounds=await page.locator('[data-testid=stImage] img').boundingBox();
    assert(bounds.width<=340&&bounds.height<=340,'Bounded image aspect ratio');
    assert(bounds.x+ bounds.width<=width+1,'Image remains in viewport');
    assert.equal(await page.getByTestId('stException').count(),0);
    if(i<6)await page.getByRole('button',{name:/Next card/}).click();
   }
   await page.getByRole('button',{name:/Previous card/}).click();
   await page.getByText('CARD 5 OF 6',{exact:true}).waitFor();
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   console.log(`${width}px: 6 ordered cards, local arrows/counter/copy, bounded image, no overflow.`);
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
