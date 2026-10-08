const {chromium}=require('playwright'),fs=require('fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const context=await browser.newContext();
 const loader=fs.readFileSync('shopify/on-demand-wall-preview/assets/sports-cave-wall-preview-loader.js','utf8');
 await context.route('**/*',r=>r.fulfill({contentType:'text/html',body:`<div class="section-main-product"><button data-sc-wall-preview-trigger>See it on your wall</button><div data-sc-wall-root></div></div><script>window.opens=[];document.querySelector('[data-sc-wall-root]').scWallOpen=()=>opens.push(new URL(location.href).searchParams.get('variant'));</script><script>${loader}</script>`}));
 const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('https://www.sportscaveshop.com/products/test?variant=123&sc_wall_preview=1');
 assert.deepEqual(await page.evaluate(()=>opens),['123']);assert.equal(new URL(page.url()).searchParams.get('variant'),'123');
 assert.equal(new URL(page.url()).searchParams.has('sc_wall_preview'),false);
 await page.addScriptTag({content:loader});assert.deepEqual(await page.evaluate(()=>opens),['123']);
 await page.goto('https://www.sportscaveshop.com/products/test?variant=456');
 assert.deepEqual(await page.evaluate(()=>opens),[]);
 await page.getByRole('button').click();assert.deepEqual(await page.evaluate(()=>opens),['456']);
 await context.route('**/*',r=>r.fulfill({contentType:'text/html',body:`<h1>Normal product page</h1><script>${loader}</script>`}));
 await page.goto('https://www.sportscaveshop.com/products/test?variant=123&sc_wall_preview=1');
 await page.getByRole('heading',{name:'Normal product page'}).waitFor();assert.deepEqual(errors,[]);
 console.log('PASS email product deep link: variant retained, existing trigger invoked once, manual trigger unchanged, safe unsupported-page fallback');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
