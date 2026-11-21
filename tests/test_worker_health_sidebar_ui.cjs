const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{for(const width of [1280,390]){
 const page=await browser.newPage({viewport:{width,height:900}});await page.goto('http://127.0.0.1:18891/');
 const sidebar=page.locator('[data-testid="stSidebar"]');await sidebar.waitFor({state:'attached'});await sidebar.locator('[class*="st-key-sidebar-disclosure-companion-"] button').last().waitFor({state:'attached'});
 // Fixture omits the top bar: use the existing shell's mobile-open class.
 if(width<821)await page.evaluate(()=>document.body.classList.add('sc-mobile-nav-open'));
 const developer=sidebar.locator('[class*="st-key-sidebar-disclosure-companion-"] button:visible').first();await developer.waitFor();await developer.scrollIntoViewIfNeeded();
 await developer.click();if(width<821)await page.evaluate(()=>document.body.classList.add('sc-mobile-nav-open'));const child=sidebar.locator('.st-key-sidebar-companion-children button:visible').first();await child.waitFor();
 assert((await page.url()).includes('page=Upload+Companion')||(await page.url()).includes('Upload%20Companion'));
 assert((await child.innerText()).includes('Companion Queues'));
 const editions=sidebar.locator('.st-key-sidebar-companion-children button').filter({hasText:'Editions Companion'});
 await editions.click();if(width<821)await page.evaluate(()=>document.body.classList.add('sc-mobile-nav-open'));
 await page.waitForURL(/page=Worker(?:\+|%20)Health/);
 const style=await developer.evaluate(el=>({height:el.getBoundingClientRect().height,bg:getComputedStyle(el).backgroundColor,font:getComputedStyle(el).fontSize}));assert(style.height<=(width<821?48:40));
 await developer.click();await page.waitForURL(/page=Upload(?:\+|%20)Companion/);if(width<821)await page.evaluate(()=>document.body.classList.add('sc-mobile-nav-open'));await developer.click();await child.waitFor({state:'hidden'});await developer.click();await child.waitFor();
 const dev=sidebar.locator('[class*="st-key-sidebar-disclosure-developer-"] button:visible').first();await dev.click();if(width<821)await page.evaluate(()=>document.body.classList.add('sc-mobile-nav-open'));
 await sidebar.locator('.st-key-sidebar-developer-children').getByText('Task Recorder',{exact:true}).waitFor();
 assert.equal(await sidebar.locator('.st-key-sidebar-developer-children').getByText('Companion Queues',{exact:true}).count(),0);
 fs.mkdirSync('output/worker-health',{recursive:true});await page.screenshot({path:`output/worker-health/sidebar-${width}.png`});
 console.log(JSON.stringify({width,defaultRoute:'Upload Companion',developer:'tools separate',collapse:'passed',developerStyle:style}));await page.close();
 }}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
