const {chromium}=require('playwright'),fs=require('fs'),crypto=require('crypto');
const port=process.argv[2]||8554,label=process.argv[3]||'after',out='docs/email-inbox-outlook-v2d-evidence';
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true}),results=[];try{for(const width of [320,390,768,1024,1440]){
 const context=await browser.newContext({viewport:{width,height:900}});await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 await context.addInitScript(()=>{window.__test={};window.addEventListener('message',e=>{if(e.data?.type==='streamlit:render')window.__test.model=e.data.args.model;});});
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(`http://127.0.0.1:${port}/?actor=${crypto.randomUUID()}&delay=0`);
 await page.frameLocator('iframe[title="support_email_page.support_email_desktop"]').locator('.conversation').first().waitFor();const f=page.frames().find(f=>f.url().includes('/component/'));
 await f.waitForFunction(()=>!window.__test.model.discovery_pending&&!window.__test.model.read_pending);
 await page.screenshot({path:`${out}/${label}-list-${width}.png`});await f.locator('.conversation').first().click();await f.locator('.email-document').first().waitFor();
 await page.screenshot({path:`${out}/${label}-reader-${width}.png`});await f.locator('[data-action="compose"][data-mode="reply"]').click();await f.locator('#editor').waitFor();
 await page.screenshot({path:`${out}/${label}-compose-${width}.png`});
 results.push({width,errors,overflow:await f.evaluate(()=>document.documentElement.scrollWidth>innerWidth),editorVisible:await f.locator('#editor').isVisible()});await context.close();
 }fs.writeFileSync(`${out}/${label}-responsive.json`,JSON.stringify(results,null,2));}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
