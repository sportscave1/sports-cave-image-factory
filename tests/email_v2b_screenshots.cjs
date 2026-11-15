const {chromium}=require('playwright'),crypto=require('crypto');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:900},ignoreHTTPSErrors:true});
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto(`http://127.0.0.1:8554/?actor=${crypto.randomUUID()}`);
  const frame=page.frameLocator('iframe[title="support_email_page.support_email_desktop"]');
  await frame.locator('.conversation').first().click();
  await frame.locator('[data-action="show_images"]').waitFor();
  await page.screenshot({path:`docs/email-inbox-outlook-v2b-evidence/privacy-blocked-${width}.png`});
  await frame.locator('[data-action="show_images"]').click();
  await frame.getByText('Images shown for this message',{exact:true}).waitFor();
  await page.screenshot({path:`docs/email-inbox-outlook-v2b-evidence/privacy-approved-${width}.png`});
  await page.close();
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
