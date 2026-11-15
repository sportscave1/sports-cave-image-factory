// Offline active Streamlit UI: all image fixtures are intercepted, never Meta.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jWZkAAAAASUVORK5CYII=','base64');
(async()=>{fs.mkdirSync('.tmp-meta-carousel',{recursive:true});const browser=await chromium.launch({channel:'chrome',headless:true});const results=[];
try{for(const [width,height] of [[1920,1080],[1440,900],[1366,768],[1024,768],[430,932],[390,844]]){
const context=await browser.newContext({viewport:{width,height},permissions:['clipboard-read','clipboard-write']});let graph=0,full=0;
await context.route('**/*',r=>{const u=new URL(r.request().url());if(u.hostname.includes('facebook')){graph++;return r.abort();}if(u.pathname.startsWith('/full/'))full++;if(/\/(thumb|full)\/\d.png/.test(u.pathname))return r.fulfill({contentType:'image/png',body:fs.readFileSync(`tests/fixtures/meta_carousel_cards/card${u.pathname.match(/(\d).png/)[1]}.png`)});return u.hostname==='127.0.0.1'?r.continue():r.abort();});
const page=await context.newPage();await page.goto('http://127.0.0.1:8532');
for(const screen of ['Meta Review','Creative Refresh']){
if(screen==='Creative Refresh')await page.getByText('Creative Refresh',{exact:true}).click();
const f=page.frameLocator('iframe').first();if(screen==='Creative Refresh')await f.locator('body.refresh').waitFor();await f.locator('.card').nth(3).waitFor();assert.equal(await f.locator('.card').count(),4);
await page.getByText('Headline 4',{exact:true}).waitFor();assert.equal(await page.getByTestId('stException').count(),0);
assert.equal(await f.getByRole('button',{name:/Next card|Previous card/}).count(),0);
const bounds=await f.locator('.card').evaluateAll(es=>es.map(e=>({x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y,w:e.getBoundingClientRect().width})));
assert(bounds.every(x=>x.y===bounds[0].y),'All cards in the same horizontal row');assert(bounds.every(x=>x.w<=220||width<600));
assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'No page overflow');
if(screen==='Meta Review')assert.equal(full,0,'No full resolution downloads before explicit request');
await f.locator('.strip').focus();await page.keyboard.press('ArrowRight');
await f.getByRole('button',{name:'COPY IMAGE URLS',exact:true}).click();await f.locator('#status').filter({hasText:'Image URLs copied'}).waitFor();
const urls=await page.evaluate(()=>navigator.clipboard.readText());const expected=await f.getByRole('link').evaluateAll(es=>es.map((e,i)=>`${i+1}. ${e.href}`).join('\n'));assert.equal(urls.replace(/\r\n/g,"\n"),expected);
const open=f.getByRole('link',{name:'Open full-resolution card 1'});const popup=page.waitForEvent('popup');await open.click();const tab=await popup;await tab.waitForLoadState('domcontentloaded');assert.equal(tab.url(),expected.split('\n')[0].slice(3));await tab.close();
// Exercise actual image clipboard then force the browser-supported URL fallback.
await f.getByRole('button',{name:'Copy image 1',exact:true}).click();await f.locator('#status').filter({hasText:/Card 1 (image|URL) copied/}).waitFor();
const frame=page.frames().find(x=>x!==page.mainFrame());await frame.evaluate(()=>Object.defineProperty(navigator.clipboard,'write',{value:()=>Promise.reject(Error('unsupported'))}));
await f.getByRole('button',{name:'Copy image 2',exact:true}).click();await f.locator('#status').filter({hasText:'Card 2 URL copied'}).waitFor();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),expected.split('\n')[1].slice(3));
assert.equal(graph,0);await page.screenshot({path:`.tmp-meta-carousel/ux-${width}-${screen.replaceAll(' ','-')}.png`});results.push({width,height,screen,cards:4,graphReads:graph,open:true,copy:true,orderedURLs:true});console.log(JSON.stringify(results.at(-1)));
}await context.close();}fs.writeFileSync('.tmp-meta-carousel/ux-browser.json',JSON.stringify(results,null,2));}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
