// Synthetic DOM only: no application server, credentials or external images.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const css = fs.readFileSync('components/design_review_gallery.css', 'utf8');
const column = body => `<div data-testid="stColumn">${body}</div>`;
const row = body => `<div data-testid="stHorizontalBlock">${body}</div>`;
const card = i => `<div class="st-key-design-review-card-${i}"><a class="sc-review-artwork"><img width="1024" height="724" alt=""></a>${row(column('<div data-testid="stCheckbox"><input type="checkbox"></div>') + column('<h3 class="sc-review-title">A very long design title for testing</h3>') + column('<a class="sc-review-edit">Edit</a>') + column('<button>Publish now</button>') + column('<button>Publish + ad</button>'))}</div>`;
(async () => {
  const browser = await chromium.launch({channel:'msedge', headless:true});
  try {
    const page = await browser.newPage();
    for (const width of [360, 768, 1280]) {
      await page.setViewportSize({width, height:1000});
      await page.setContent(`<style>*{box-sizing:border-box}body{margin:12px;font:16px Arial}[data-testid="stHorizontalBlock"]{display:flex;gap:16px}[data-testid="stColumn"]{flex:1;min-width:0}button{font:inherit}</style>${css}<main class="st-key-design-review-gallery"><div class="st-key-design-review-selection">${row(column('0 selected') + column('<div class="st-key-design-review-enqueue"><button>Add to queue</button></div>') + column('<div class="st-key-design-review-trash"><button aria-label="Delete">×</button></div>'))}</div><div class="st-key-design-review-grid">${row(column(card(1)) + column(card(2)))}</div></main>`);
      const metrics = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth > innerWidth,
        cards: [...document.querySelectorAll('.sc-review-artwork')].map(el => ({width:el.clientWidth, height:el.clientHeight})),
        buttons: [...document.querySelectorAll('button,.sc-review-edit')].map(el => {const r=el.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width};})
      }));
      assert.equal(metrics.overflow, false, `page overflow at ${width}`);
      assert.ok(metrics.cards.every(card => Math.abs(card.width / card.height - 1024/724) < .02));
      assert.ok(metrics.buttons.every(button => button.left >= 0 && button.right <= width && button.width > 20));
      console.log(`PASS: ${width}px — bounded artwork, visible controls, no horizontal overflow`);
    }
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
