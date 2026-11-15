const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{for(const width of [1280,390]){
 const page=await browser.newPage({viewport:{width,height:900}});await page.goto('http://127.0.0.1:18891/');
 const sidebar=page.locator('[data-testid="stSidebar"]');await sidebar.waitFor({state:'attached'});await sidebar.locator('[class*="st-key-sidebar-disclosure-developer-"] button').last().waitFor({state:'attached'});
 // Fixture omits the top bar: use the existing shell's mobile-open class.
 if(width<821)await page.evaluate(()=>document.body.classList.add('sc-mobile-nav-open'));
 const developer=sidebar.locator('[class*="st-key-sidebar-disclosure-developer-"] button:visible').first();await developer.waitFor();await developer.scrollIntoViewIfNeeded();
 await developer.click();if(width<821)await page.evaluate(()=>document.body.classList.add('sc-mobile-nav-open'));const child=sidebar.locator('.st-key-sidebar-developer-children button:visible').first();await child.waitFor();
 assert((await page.url()).includes('page=Worker+Health')||(await page.url()).includes('Worker%20Health'));
 const devMode=sidebar.locator('.st-key-sidebar-developer-children a:visible').first();assert((await devMode.getAttribute('href')).includes('dev_mode=1'));assert.equal(await devMode.getAttribute('target'),'_blank');
 const devText=await devMode.locator('p').evaluate(el=>getComputedStyle(el).color);assert.equal(devText,'rgb(238, 238, 235)');
 const style=await developer.evaluate(el=>({height:el.getBoundingClientRect().height,bg:getComputedStyle(el).backgroundColor,font:getComputedStyle(el).fontSize}));assert(style.height<=(width<821?48:40));
 await developer.click();await child.waitFor({state:'hidden'});await developer.click();await child.waitFor();
 fs.mkdirSync('output/worker-health',{recursive:true});await page.screenshot({path:`output/worker-health/sidebar-${width}.png`});
 console.log(JSON.stringify({width,defaultRoute:'Worker Health',devMode:'existing separate tab',collapse:'passed',developerStyle:style}));await page.close();
 }}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
