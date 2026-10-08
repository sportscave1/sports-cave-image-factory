// Measured real browser interactions over synthetic SQL; external requests blocked.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
const context=await browser.newContext({viewport:{width:1440,height:1000}});
await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
if(process.env.EMAIL_SLOW){const cdp=await context.newCDPSession(page);await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:150,downloadThroughput:200000,uploadThroughput:100000});}
await page.goto('http://127.0.0.1:8543/');await page.locator('.sc-home-row').first().waitFor();
async function count(){const prior=await page.locator('#email-profile').innerText();await page.getByRole('button',{name:'Profile snapshot',exact:true}).click();await page.waitForFunction(old=>document.querySelector('#email-profile')?.textContent!==old,prior);return JSON.parse(await page.locator('#email-profile').innerText());}
async function sample(){await page.evaluate(()=>{window.samples=[];window.sampling=true;window.started=performance.now();function tick(){if(!window.sampling)return;const home=document.querySelector('.sc-home-kpis'),editor=document.querySelector('.st-key-crm-selected-campaign');window.samples.push({ms:performance.now()-window.started,home:!!home,editor:!!editor,giant:[...document.querySelectorAll('.sc-home-icon img')].some(e=>e.getBoundingClientRect().width>40)});requestAnimationFrame(tick)}tick()});}
const result={};
for(const kind of ['cold','warm']){
 const before=await count();await page.locator('.st-key-crm-home-table [data-testid=stPopoverButton]').first().click();
 await sample();const t=Date.now();await page.getByRole('button',{name:'Edit',exact:true}).click();await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();
 result[kind]={editorMs:Date.now()-t};await page.locator('.st-key-crm-composer-preview iframe').waitFor();
 const frames=await page.evaluate(()=>{window.sampling=false;return window.samples});result[kind].overlapFrames=frames.filter(f=>f.home&&f.editor).length;result[kind].giantFrames=frames.filter(f=>f.giant).length;
 result[kind].openReads=(await count()).queries-before.queries;
 await page.evaluate(()=>window.previewFrame=document.querySelector('.st-key-crm-composer-preview iframe'));
 const snapshots=await count();let tabTimes=[];for(const tab of ['Editor','Templates','Settings','Editor']){const at=Date.now();await page.getByRole('tab',{name:tab,exact:true}).click();if(tab==='Editor')await page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]').getByRole('textbox').first().waitFor();else if(tab==='Templates')await page.getByText('Email defaults',{exact:true}).waitFor();else await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();tabTimes.push(Date.now()-at);}
 assert.equal(await page.evaluate(()=>window.previewFrame===document.querySelector('.st-key-crm-composer-preview iframe')),true,'Tab changes preserve the preview iframe');
 result[kind].tabMs=tabTimes;const afterTabs=await count();result[kind].tabReads=afterTabs.queries-snapshots.queries;result[kind].tabDefaultReads=afterTabs.defaults-snapshots.defaults;
 const area=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]').getByRole('textbox').first();await area.waitFor();
 await page.evaluate(()=>{window.longTasks=[];window.taskObserver=new PerformanceObserver(l=>window.longTasks.push(...l.getEntries().map(e=>e.duration)));window.taskObserver.observe({type:'longtask',buffered:false})});
 const typed=' typing '+kind+' '+Date.now();await area.press('End');await area.pressSequentially(typed,{delay:15});await area.press('Tab');
 await page.waitForFunction(text=>document.querySelector('.st-key-crm-composer-preview iframe')?.contentDocument?.body?.textContent.includes(text),typed);await page.evaluate(()=>window.scCampaignFlushRecovery?.());
 await page.getByText('Saved',{exact:true}).last().waitFor();result[kind].longTasks=await page.evaluate(()=>{window.taskObserver.disconnect();return window.longTasks});
 const returnBefore=await count();const back=Date.now();await page.getByRole('button',{name:'← Campaigns',exact:true}).click();await page.locator('.sc-home-row').first().waitFor().catch(async e=>{console.log('diagnostics',await count());console.log((await page.locator('body').innerText()).slice(-6000));await page.screenshot({path:'tmp/email-slow-error.png'});throw e;});result[kind].backMs=Date.now()-back;result[kind].backReads=(await count()).queries-returnBefore.queries;
 if(!process.env.EMAIL_BASELINE){assert.equal(result[kind].overlapFrames,0);assert.equal(result[kind].giantFrames,0);}
}
assert.deepEqual(errors,[]);fs.writeFileSync('tmp/email-performance-'+(process.env.EMAIL_BASELINE?'before':'after')+(process.env.EMAIL_SLOW?'-slow':'')+'.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});



