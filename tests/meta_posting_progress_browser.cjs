// Run against the explicit mocked Streamlit fixture on loopback only.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({channel: 'chrome', headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 900}});
    await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:8891');
    await page.getByRole('button', {name: 'Create 3 Paused Meta Ads', exact: true}).waitFor();
    const start = Date.now();
    await page.getByRole('button', {name: 'Create 3 Paused Meta Ads', exact: true}).click();
    await page.getByRole('heading', {name: 'Creating your Meta ads', exact: true}).waitFor();
    const responseMs = Date.now() - start;
    await page.waitForURL(/meta_posting_job=/);
    const identity = new URL(page.url()).searchParams.get('meta_posting_job');
    await page.reload();
    await page.getByRole('heading', {name: 'Creating your Meta ads', exact: true}).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('meta_posting_job'), identity);
    await page.getByRole('button', {name: 'Continue mocked Meta job', exact: true}).click();
    await page.getByRole('button', {name: 'Retry incomplete steps', exact: true}).waitFor({timeout: 20000});
    await page.screenshot({path: 'tmp/meta-posting-partial.png', fullPage: true});
    // Full refresh also enables the fixture's formerly failing mocked request.
    await page.reload();
    await page.getByRole('button', {name: 'Retry incomplete steps', exact: true}).click();
    const success = process.env.POST_AD_COMPACT_PROGRESS ? 'Ads created successfully in Meta' : '3 Meta ads created successfully';
    await page.getByText(success, {exact: false}).first().waitFor({timeout: 20000}).catch(async error => {
      console.error('Mocked posting result:', await page.locator('body').innerText());
      throw error;
    });
    await page.getByRole('link', {name: 'Open in Ads Manager', exact: true}).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('meta_posting_job'), identity);
    await page.screenshot({path: 'tmp/meta-posting-complete.png', fullPage: true});
    await page.reload();
    await page.getByText(success, {exact: false}).first().waitFor();
    assert.equal(await page.locator('[data-testid="stException"]').count(), 0);
    assert.equal(await page.getByRole('progressbar').count(), 1);
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({responseMs, refreshRestored: true, partialRetry: true, completedRestored: true, mobileOverflow: false}));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
