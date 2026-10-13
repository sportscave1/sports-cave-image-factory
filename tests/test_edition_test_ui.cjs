const { chromium } = require('playwright'), fs = require('node:fs'), assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    for (const width of [1366, 390]) {
      const context = await browser.newContext({ viewport: { width, height: 850 } });
      let loads = 0;
      await context.route('**/*', route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/') { loads++; return route.fulfill({ contentType: 'text/html', body: '<a id="pilot" href="/edition-jpg-test#TEST JPG">TEST JPG</a><iframe src="/component"></iframe>' }); }
        if (path === '/component') return route.fulfill({ contentType: 'text/html', body: fs.readFileSync('components/psd_picker/index.html', 'utf8') });
        if (path === '/edition-jpg-test') return route.fulfill({ contentType: 'text/html', body: fs.readFileSync('components/edition_test/index.html', 'utf8') });
        return route.abort();
      });
      const page = await context.newPage(); await page.goto('http://edition-pilot.local.test/');
      await page.waitForFunction(() => !!window.SportsCavePsdPicker);
      await page.locator('#pilot').focus(); await page.locator('#pilot').click();
      const frame = page.frameLocator('dialog iframe'); await frame.locator('#generate').waitFor();
      assert.equal(await frame.locator('#preview').isVisible(), false);
      assert.equal(await frame.locator('#download').isVisible(), false);
      assert.equal(await frame.locator('body').evaluate(e => e.scrollWidth <= innerWidth), true);
      await frame.locator('#generate').focus(); await page.keyboard.press('Escape');
      await page.locator('dialog').waitFor({ state: 'detached' });
      assert.equal(await page.evaluate(() => document.activeElement.id), 'pilot');
      assert.equal(loads, 1); await context.close();
    }
    console.log('Edition pilot: desktop/mobile modal, hidden empty preview/download, Escape/focus restoration and no Orders reload passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
