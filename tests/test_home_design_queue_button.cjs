const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({channel:'msedge', headless:true});
  try {
    const page = await browser.newPage();
    const template = fs.readFileSync('components/morning_brief_actions.html', 'utf8');
    const row = '<article class="sc-brief-row"><small class="sc-brief-status attention">Needs attention</small>' +
      '<div class="sc-brief-actions"><button data-design-key="fixture">Add to Queue</button></div></article>';
    const html = template.replace('<!-- RECOMMENDATIONS -->', row);
    let requests = 0, release;
    await page.route('https://queue.example.test/**', async route => {
      if (route.request().method() !== 'POST') return route.fulfill({contentType:'text/html', body:html});
      requests++;
      await new Promise(resolve => { release = resolve; });
      await route.fulfill({contentType:'application/json', body:JSON.stringify({added:true})});
    });
    await page.goto('https://queue.example.test/');
    const button = page.locator('[data-design-key]');
    await button.click();
    await page.waitForFunction(() => document.querySelector('[data-design-key]').disabled);
    await button.evaluate(el => el.click());
    assert.equal(requests, 1);
    release();
    await page.waitForFunction(() => document.querySelector('.sc-brief-status').textContent.includes('Pending'));
    assert.equal(await button.isDisabled(), false);
    assert.equal(await page.locator('.sc-brief-toast').textContent(), 'Added to the Design Companion queue.');
    await button.click();
    await page.waitForFunction(() => document.querySelector('[data-design-key]').disabled);
    assert.equal(requests, 2);
    release();
    await page.waitForFunction(() => !document.querySelector('[data-design-key]').disabled);
    assert.equal(page.context().pages().length, 1);
    console.log('PASS: queue POST, immediate disabling, duplicate-click protection, pending status, no ChatGPT tab.');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
