// Shared acceptance suite against synthetic real Streamlit fragments only.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const baseline=process.env.UNIFIED_FLOW_BASELINE==='1',port=process.env.FLOW_PORT||(baseline?18750:18749);
const titles={abandoned:'Abandoned checkouts',welcome:'Marketing subscribers',post_purchase:'Orders',win_back:'Inactive purchasers',...(!baseline?{fulfilled:'Recipients'}:{})};
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true}),report=[];
try{for(const width of (process.env.FLOW_DESKTOP_ONLY||baseline?[1440]:[1440,390]))for(const [kind,title] of Object.entries(titles).filter(([k])=>!process.env.FLOW_ONLY||process.env.FLOW_ONLY===k)){
 const p=await browser.newPage({viewport:{width,height:1000}});
 await p.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 await p.goto(`http://127.0.0.1:${port}/?flow=${kind}&delay=${process.env.FLOW_READ_DELAY||.02}`);
 const summary=p.locator('[data-testid="stExpander"] summary').first();await summary.waitFor();
 const start=Date.now();await summary.click();const f=p.frameLocator('iframe').first();
 await p.locator('iframe').first().waitFor({state:'visible'});await f.locator('tbody tr').nth(49).waitFor({timeout:30000});const coldMs=Date.now()-start;
 const checks=f.locator('tbody input');await checks.first().check();await p.waitForTimeout(400);
 if(!baseline)assert.equal(await checks.first().isChecked(),true);
 await f.locator('.wrap').evaluate(e=>e.scrollTop=210);
 await p.evaluate(()=>{window.observed=document.querySelector('iframe');window.remounts=0;new MutationObserver(()=>{const n=document.querySelector('iframe');if(n&&n!==window.observed){window.remounts++;window.observed=n}}).observe(document.body,{childList:true,subtree:true})});
 // More than two cache TTLs; every source must survive the same refresh window.
 await p.waitForTimeout(Number(process.env.FLOW_DWELL_MS)||65000);
 if(!baseline)assert.equal(await p.locator('details').first().getAttribute('open'),'');
 if(!baseline)assert.equal(await checks.first().isChecked(),true);
 if(!baseline)assert.equal(await f.locator('.wrap').evaluate(e=>e.scrollTop),210);
 if(!baseline)assert.equal(await p.evaluate(()=>window.remounts),0);
 const preservedScroll=await f.locator('.wrap').evaluate(e=>e.scrollTop),remounts=await p.evaluate(()=>window.remounts);
 const metrics=JSON.parse((await p.getByText('FIXTURE_METRICS ',{exact:false}).innerText()).split('FIXTURE_METRICS ')[1]);
 if(baseline){
  await summary.click();await p.locator('iframe').first().waitFor({state:'hidden'});await p.waitForTimeout(300);const warm=Date.now();await summary.click();await p.locator('iframe').first().waitFor({state:'visible'});await f.locator('tbody tr').first().waitFor();
  report.push({kind,width,coldMs,preservedScroll,remounts,warmMs:Date.now()-warm,readsDuringWindow:metrics.reads,windowSeconds:(Number(process.env.FLOW_DWELL_MS)||65000)/1000,readSamples:metrics.samples});
  fs.writeFileSync('.tmp-unified-flow/before-ui.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report.at(-1)));await p.close();continue;
 }
 const next=p.getByRole('button',{name:kind==='abandoned'?'Next checkouts':'Next',exact:true});
 await next.click();await f.getByRole('button',{name:'Details Fixture customer 50',exact:true}).waitFor();
 await f.locator('thead input').check();await p.waitForTimeout(250);await f.locator('thead input').uncheck();await p.waitForTimeout(250);
 await p.getByRole('button',{name:kind==='abandoned'?'Previous checkouts':'Previous',exact:true}).click();
 await f.getByRole('button',{name:'Details Fixture customer 0',exact:true}).waitFor();
 if(!baseline)assert.equal(await checks.first().isChecked(),false);
 const search=p.getByRole('textbox',{name:'Search and filter',exact:true});
 await search.fill('fixture1@example.test');await search.press('Enter');await f.getByRole('button',{name:'Details Fixture customer 1',exact:true}).waitFor();await f.locator('tbody tr').nth(1).waitFor({state:'detached'});
 await f.locator('tbody tr').first().waitFor();assert.equal(await f.locator('tbody tr').count(),1);
 await summary.click();await p.locator('iframe').first().waitFor({state:'hidden'});await p.waitForTimeout(300);const warm=Date.now();await summary.click();await p.locator('iframe').first().waitFor({state:'visible'});
 await f.locator('tbody tr').first().waitFor();const warmMs=Date.now()-warm;await p.waitForTimeout(300);
 if(!baseline){assert.equal(await search.inputValue(),'fixture1@example.test');await f.locator('tbody tr').first().waitFor();assert.equal(await f.locator('tbody tr').count(),1);}
 assert.equal(await p.locator('[data-testid="stException"]').count(),0);
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 if(!baseline){await search.waitFor({state:'visible'});await p.waitForTimeout(200);}if(!baseline)await p.screenshot({path:`.tmp-unified-flow/${kind}-${width}.png`,fullPage:true});
 report.push({kind,width,coldMs,warmMs,readsDuringWindow:metrics.reads,windowSeconds:(Number(process.env.FLOW_DWELL_MS)||65000)/1000,readSamples:metrics.samples});
 fs.writeFileSync(`.tmp-unified-flow/${process.env.FLOW_REPORT||'after-ui'}.json`,JSON.stringify(report,null,2));console.log(JSON.stringify(report.at(-1)));await p.close();
}
fs.writeFileSync(`.tmp-unified-flow/${process.env.FLOW_REPORT||(baseline?'before-ui':'after-ui')}.json`,JSON.stringify(report,null,2));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
