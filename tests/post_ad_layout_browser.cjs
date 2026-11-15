// Offline fixture only. Optional BEFORE=1 records the original layout.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({channel:'chrome', headless:true});
  try {
    const page = await browser.newPage();
    const results = [];
    for (const width of [1440, 1280, 768, 390]) {
      await page.setViewportSize({width, height:900});
      const start = Date.now();
      await page.goto(`http://127.0.0.1:${Number(process.env.PORT || 8537)}`);
      await page.getByRole('button', {name: process.env.BEFORE ? 'Create 3 Paused Meta Ads' : 'Create Ad', exact:true}).waitFor();
      const loadMs = Date.now()-start;
      await page.waitForTimeout(250); // Allow fonts and responsive columns to settle.
      const metrics = await page.evaluate(() => {
        const main = document.querySelector('[data-testid="stMain"]');
        return {height:main.scrollHeight, overflow:document.documentElement.scrollWidth>innerWidth,
                headingTop:document.querySelector('h1').getBoundingClientRect().top};
      });
      assert.equal(metrics.overflow, false);
      assert.equal(await page.locator('[data-testid="stException"]').count(), 0);
      if (!process.env.BEFORE) {
        for (const text of ['Meta connected · ready','Advanced Meta Diagnostics','Recent Posting jobs'])
          assert.equal(await page.getByText(text,{exact:true}).count(),0);
      }
      if(width===1440) await page.screenshot({path:`tmp/post-ad-${process.env.BEFORE?'before':'after'}.png`,fullPage:true});
      results.push({width,loadMs,...metrics});
      if (!process.env.BEFORE) {
        await page.getByRole('button', {name:'Carousel',exact:true}).click();
        await page.getByText('CAROUSEL CARD 5',{exact:true}).waitFor();
        assert.equal(await page.getByRole('button',{name:'Create Ad',exact:true}).count(),1);
        assert.equal(await page.locator('[data-testid="stFileUploader"]').count(),6);
        assert.equal(await page.locator('[data-testid="stTextArea"]').count(),5);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),true);
      }
    }
    console.log(JSON.stringify(results,null,2));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
