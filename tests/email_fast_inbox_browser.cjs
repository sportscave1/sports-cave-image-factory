// Local synthetic provider only; requests outside loopback are blocked.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());
  const started=Date.now();await page.goto('http://127.0.0.1:8534');
  const mail=page.frameLocator('iframe[title="support_email_page.support_email_desktop"]');
  await mail.locator('.conversation').first().waitFor({timeout:20000});
  console.log('Cold fixture navigation to list:',Date.now()-started,'ms (includes Streamlit startup and synthetic provider delay)');
  await mail.locator('.conversation').nth(1).click();
  await mail.locator('.conversation.selected').waitFor();
  await mail.locator('.message-body').first().waitFor({timeout:20000});
  const start=Date.now();await mail.locator('.conversation').nth(0).click();
  assert.match(await mail.locator('.conversation').nth(0).getAttribute('class'),/selected/);
  console.log('Row selection:',Date.now()-start,'ms');
  // The mailbox shell intentionally hides Streamlit's fixture-only sidebar.
  await page.getByRole('checkbox',{name:'Simulate mailbox outage'}).evaluate(node=>node.click());
  await mail.locator('.statusbar').filter({hasText:/Reconnecting|unavailable/}).waitFor({timeout:20000});
  assert.ok(await mail.locator('.conversation').count()>0,'Cached list remains during outage');
  await page.getByRole('checkbox',{name:'Simulate mailbox outage'}).evaluate(node=>node.click());
  await mail.locator('.statusbar').filter({hasText:'Connected'}).waitFor({timeout:20000});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.getByTestId('stException').count(),0);
  assert.deepEqual(errors,[]);
  console.log('PASS: selection, cached outage, reconnect, narrow viewport, no runtime exceptions or real email sends.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
