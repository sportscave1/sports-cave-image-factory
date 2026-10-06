const { chromium } = require('playwright');
const fs = require('fs');
const assert = require('assert');
(async () => {
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const page = await browser.newPage();
  await page.clock.install();
  let requests = [];
  await page.route('https://fixture.test/**', async route => {
    if (route.request().url().includes('/api/os/security/session')) {
      requests.push(JSON.parse(route.request().postData()).action);
      return route.fulfill({contentType:'application/json',body:'{"ok":true}'});
    }
    return route.fulfill({contentType:'text/html',body:'<div data-testid="stImage"><img></div><div class="st-key-files-explorer"><div data-testid="stImage"><img></div></div><input id="draft" value="Unsaved draft">'});
  });
  await page.goto('https://fixture.test/');
  const policy = {appSelection:true,appPrinting:true,appImageDragging:true,appRightClick:true,appCopyDeterrence:true,appWatermark:false,blurOnFocusLoss:true,autoLockMinutes:15};
  const script = fs.readFileSync('app-protection.js','utf8').replace('SC_POLICY',JSON.stringify(policy)).replace('SC_NAME','"Fixture user"');
  await page.addScriptTag({content:script});
  await page.addScriptTag({content:script});
  assert.equal(await page.locator('#sc-app-privacy-shade').count(),1);
  assert.equal(await page.locator('[data-sc-protected]').count(),1);
  await page.clock.fastForward(15*60*1000);
  await page.getByRole('button',{name:'Unlock',exact:true}).waitFor();
  assert.equal(requests.filter(x=>x==='lock').length,1);
  assert.equal(await page.locator('#draft').inputValue(),'Unsaved draft');
  await page.getByRole('textbox',{name:'Current password',exact:true}).fill('fixture-password');
  await page.getByRole('button',{name:'Unlock',exact:true}).click();
  await page.waitForFunction(()=>getComputedStyle(document.querySelector('#sc-app-privacy-shade')).display==='none');
  assert.equal(requests.filter(x=>x==='reauth').length,1);
  assert.equal(await page.locator('#draft').inputValue(),'Unsaved draft');
  await page.evaluate(value=>window.__scAppPrivacy.update(value,'Fixture user'),{...policy,rememberedSession:true});
  await page.clock.fastForward(16*60*1000);
  assert.equal(requests.filter(x=>x==='lock').length,1);
  assert.equal(await page.locator('#sc-app-privacy-shade').evaluate(node=>getComputedStyle(node).display),'none');
  await browser.close();
  console.log('App privacy: remembered sessions retain access while ordinary sessions still idle-lock.');
})().catch(error=>{console.error(error);process.exit(1);});
