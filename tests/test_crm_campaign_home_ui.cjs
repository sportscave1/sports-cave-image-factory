// Run against campaign_home_preview.py only. Block all non-loopback traffic.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const context=await browser.newContext();
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();
  for(const [width,height] of [[1920,1080],[1366,768],[750,900],[390,844]]){
   await page.setViewportSize({width,height});await page.goto('http://127.0.0.1:8531');
   await page.getByRole('button',{name:'+ New campaign',exact:true}).waitFor();
   await page.getByText('Ranked by attributed orders · all time',{exact:true}).waitFor();
   await page.locator('.sc-home-kpis').waitFor();
   await page.waitForTimeout(600);
   assert.equal(await page.getByTestId('stException').count(),0);
   const bounds=await page.evaluate(()=>({body:document.documentElement.scrollWidth,
     main:document.querySelector('.st-key-crm-home-main').getBoundingClientRect().toJSON(),
     rail:document.querySelector('.st-key-crm-home-rail').getBoundingClientRect().toJSON(),
     cards:getComputedStyle(document.querySelector('.sc-home-kpis')).gridTemplateColumns.split(' ').length}));
   assert(bounds.body<=width,'No document overflow');
   if(width<=1500)assert(bounds.rail.top>bounds.main.top,'Rail below at smaller widths');
   else assert(bounds.rail.left>bounds.main.left,'Rail beside on desktop');
   assert.equal(bounds.cards,width>1500?5:width>700?3:2);
   if(process.env.CAMPAIGN_HOME_EVIDENCE_DIR)await page.screenshot({path:path.join(process.env.CAMPAIGN_HOME_EVIDENCE_DIR,'campaign-home-'+width+'.png'),fullPage:true});
   console.log(width+': contained, '+bounds.cards+' KPIs across, responsive rail passed');
  }
 } finally {await browser.close();}
})();
