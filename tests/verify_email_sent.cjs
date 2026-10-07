// Local fixture only. SMTP, IMAP and audit are mocked inside email_send_preview.py.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const output=path.resolve('artifacts/email-sent-verification');
fs.mkdirSync(output,{recursive:true});
(async()=>{
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const results=[];
  try {
    for(const [scenario,width,height] of [['success',1440,900],['success',1920,1080],['copy_failure',1440,900],['rejected',1440,900],['unknown',1440,900],['server',1440,900],['delayed',1440,900]]){
      const context=await browser.newContext({viewport:{width,height}});
      await context.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
      const page=await context.newPage(),errors=[];
      page.on('pageerror',e=>errors.push(e.message));
      await page.goto('http://127.0.0.1:8506/?scenario='+scenario+'&account=staff');
      const mail=page.frameLocator('iframe[title="support_email_page.support_email_desktop"]');
      await mail.locator('[data-action="send"]').waitFor();
      assert.equal(await page.locator('.fixture-metrics').getAttribute('data-submissions'),'0');
      // A second physical click and keyboard shortcut must not create another send.
      await mail.locator('[data-action="send"]').click();
      await mail.locator('#send-status').filter({hasText:'Sending email…'}).waitFor();
      assert.equal(await mail.locator('[data-action="send"]').isDisabled(),true);
      assert.equal(await mail.locator('.compose-footer progress').count(),0);
      const progressBox=await mail.locator('#send-status').boundingBox();
      const toolbarBox=await mail.locator('.topbar').boundingBox();
      assert.ok(progressBox.y>=toolbarBox.y+toolbarBox.height-1 && progressBox.y<toolbarBox.y+toolbarBox.height+10);
      await mail.locator('body').press('Control+Enter');
      assert.equal(await mail.locator('progress').count(),1);
      if(['rejected','unknown'].includes(scenario)){
        await mail.locator('#send-status').filter({hasText:scenario==='rejected'?'Email not sent':'Confirming original send'}).waitFor();
        assert.equal(await page.locator('.fixture-metrics').getAttribute('data-copies'),'0');
        assert.equal(await mail.locator('.sent-receipt').count(),0);
      }else{
        await mail.locator('.sent-receipt').filter({hasText:'✓ Sent'}).waitFor();
        await mail.locator('.folder.selected[data-folder="INBOX.Sent Items"]').waitFor();
        assert.equal(await mail.locator('[aria-label="Compose mail"]').count(),0);
        if(scenario==='copy_failure'){
          await mail.locator('.reading').filter({hasText:'This is a fabricated send verification.'}).waitFor();
          assert.equal(await page.locator('.fixture-metrics').getAttribute('data-copies'),'2');
        }else{
          await mail.locator('.reading').filter({hasText:'This is a fabricated send verification.'}).waitFor({timeout:25000});
          assert.equal(await page.locator('.fixture-metrics').getAttribute('data-copies'),scenario==='success'?'1':'0');
        }
        assert.match(await mail.locator('.conversation.selected').innerText(),/Local .* send fixture/);
        assert.match(await mail.locator('.reading').innerText(),/john@example.test/);
        await mail.getByRole('button',{name:'↻ Refresh',exact:true}).click();
        await mail.locator('#mail:not(.busy)').waitFor();
        await mail.locator('.topbar [data-action="refresh"]:enabled').waitFor();
        // Reopening cached Sent content must not leave the reading-pane actions disabled.
        await mail.locator('.conversation.selected').click();
        await mail.locator('.reading [data-mode="reply"]:enabled').waitFor();
        assert.equal(await mail.locator('progress').count(),0);
        const box=await mail.locator('.workspace').boundingBox();
        assert.ok(box.height>height-250,'Mailbox should fill the window below compact status');
      }
      assert.equal(await page.locator('.fixture-metrics').getAttribute('data-submissions'),'1');
      assert.deepEqual(errors,[]);
      await page.screenshot({path:path.join(output,`${scenario}-${width}.png`),fullPage:true});
      results.push({scenario,width,height,result:'passed'});
      await context.close();
    }
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(results,null,2));
    console.log(JSON.stringify(results));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
