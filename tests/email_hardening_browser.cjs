// Run against the local fabricated Inbox + disposable PostgreSQL only.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];
  page.on('dialog',dialog=>dialog.accept());
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>{
    const url=new URL(route.request().url());
    return ['127.0.0.1','localhost'].includes(url.hostname)?route.continue():route.abort();
  });
  await page.goto('http://127.0.0.1:8514');
  const frame=page.frameLocator('iframe[title="support_email_page.support_email_desktop"]');
  await frame.getByRole('button',{name:'New mail',exact:false}).click();
  await frame.locator('#draft-to').fill('fixture@example.test');
  await frame.locator('#draft-subject').fill('Persistent browser fixture');
  await frame.locator('#editor').fill('Draft survives typing and refresh.');
  await frame.locator('#draft-save-status').filter({hasText:'Saved'}).waitFor();
  const content=page.frames().find(f=>f.url().includes('/component/support_email_page'));
  await content.evaluate(()=>{
   window.probe=document.querySelector('#editor');window.probe.focus();
   const range=document.createRange();range.selectNodeContents(window.probe);range.collapse(false);
   window.getSelection().removeAllRanges();window.getSelection().addRange(range);
   window.probeOffset=window.getSelection().anchorOffset;
  });
  await page.evaluate(()=>{const f=[...document.querySelectorAll('iframe')].find(f=>f.title==='support_email_page.support_email_desktop');f.contentWindow.postMessage({type:'sc:email-change',version:'fixture-background-change'},'*');});
  await page.waitForTimeout(1800);
  assert.equal(await content.evaluate(()=>window.probe===document.querySelector('#editor')),true);
  assert.equal(await content.evaluate(()=>document.activeElement===window.probe),true);
  assert.equal(await content.evaluate(()=>window.getSelection().anchorOffset===window.probeOffset),true);
  assert.equal(await frame.locator('#editor').innerText(),'Draft survives typing and refresh.');
  await page.screenshot({path:'output/email-hardening-composer.png',fullPage:true});
  await page.reload();
  await frame.locator('#editor').waitFor();
  assert.equal(await frame.locator('#draft-to').inputValue(),'fixture@example.test');
  assert.equal(await frame.locator('#draft-subject').inputValue(),'Persistent browser fixture');
  assert.equal(await frame.locator('#editor').innerText(),'Draft survives typing and refresh.');
  await frame.locator('#editor').press('Escape');
  await frame.getByRole('button',{name:'Drafts',exact:true}).click();
  await page.waitForTimeout(1500);
  if(!await frame.locator('[data-action="open_local_draft"]').count()){
    await page.screenshot({path:'output/email-hardening-drafts-debug.png',fullPage:true});
    throw new Error('Saved draft list missing: '+await frame.locator('.statusbar').innerText()+' / '+await frame.locator('.listpane').innerText());
  }
  await frame.locator('[data-action="open_local_draft"]').filter({hasText:'Persistent browser fixture'}).first().click();
  assert.equal(await frame.locator('#editor').innerText(),'Draft survives typing and refresh.');
  await frame.getByRole('button',{name:'Send',exact:true}).click();
  await frame.locator('.sent-receipt').filter({hasText:'Persistent browser fixture'}).waitFor();
  await frame.getByText('View sent message',{exact:true}).click();
  assert.match(await frame.locator('.sent-receipt').innerText(),/Draft survives typing and refresh/);
  await page.reload();
  await frame.locator('.sent-receipt').filter({hasText:'Persistent browser fixture'}).waitFor();
  assert.deepEqual(errors,[]);
  console.log('PASS: desktop, SQL autosave, background DOM/focus/caret, reload, Drafts reopen, mocked SMTP acceptance receipt and restart; zero runtime errors. No real mail sent.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
