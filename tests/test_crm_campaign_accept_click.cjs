// Real Streamlit/React controls; fabricated receipts, loopback traffic only.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  for(const slow of (process.env.CAMPAIGN_CLICK_FAST?[false]:[false,true]))for(const baseline of [true,false]){
   const context=await browser.newContext();
   await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
   const page=await context.newPage();
   if(slow){const cdp=await context.newCDPSession(page);await cdp.send('Network.enable');
    await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:250,downloadThroughput:150000,uploadThroughput:75000});}
   await page.goto('http://127.0.0.1:'+(baseline?'8526':'8525')+'/?case='+Date.now());
   await page.getByRole('button',{name:'Review & send',exact:true}).click();
   const button=page.getByRole('button',{name:'Send to 1095 recipients',exact:true});
   await button.waitFor();
   await page.waitForTimeout(350);
   const before=await button.evaluate(b=>({disabled:b.disabled,text:b.textContent}));
   const box=await button.boundingBox();
   await page.mouse.click(box.x+box.width/2,box.y+box.height/2,{clickCount:!baseline&&slow?4:1});
   let data;
   if(baseline){await page.waitForTimeout(2000);}
   else{
    await page.getByText('Fixture accepted jobs: 1',{exact:true}).waitFor({timeout:15000});
    assert.equal(await page.getByRole('dialog').count(),0);
    const metrics=JSON.parse(await page.locator('#fixture-client-timings').getAttribute('data-timings'));
    data=metrics;
    assert(metrics.feedback>=metrics.confirmClick&&metrics.feedback-metrics.confirmClick<100,'Immediate click acknowledgement');
    await page.reload();
    await page.getByText('Fixture accepted jobs: 1',{exact:true}).waitFor();
    assert.equal(await page.getByTestId('stException').count(),0);
   }
   data??=JSON.parse(await page.locator('#fixture-client-timings').getAttribute('data-timings')||'{}');
   console.log(JSON.stringify({baseline,slow,before,timings:data,home:await page.locator('.sc-home-row').count(),dialog:await page.getByRole('dialog').count()}));
   await context.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
