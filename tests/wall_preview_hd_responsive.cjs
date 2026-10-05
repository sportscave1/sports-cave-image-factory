// Local-only responsive contract. Launch tests/wall_preview_hd_ui_fixture.py on port 8876.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const page=await browser.newPage();
  await page.route('**/*',route=>route.request().url().startsWith('http://127.0.0.1:8876')?
   route.continue():route.abort());
  await page.goto('http://127.0.0.1:8876');
  await page.locator('.sc-wall-card').first().waitFor();
  for(const width of [1920,1366,750,390,320]){
   await page.setViewportSize({width,height:1000});
   await page.waitForTimeout(100);
   const layout=await page.evaluate(()=>({
    overflowing:document.documentElement.scrollWidth>innerWidth+1,
    cards:[...document.querySelectorAll('.sc-wall-card')].map(c=>{
     const r=c.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width};})}));
   assert.equal(layout.overflowing,false,`Page overflow at ${width}`);
   for(const card of layout.cards) assert.ok(card.width>0&&card.right<=width+1&&card.left>=0,`Card clipped at ${width}`);
   await page.getByText('MARKETING USE: ALLOWED',{exact:true}).waitFor();
   await page.getByText('EMAIL: SUBSCRIBED',{exact:true}).waitFor();
   console.log(`PASS Inbox ${width}px: no horizontal overflow, independent badges visible`);
  }
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
