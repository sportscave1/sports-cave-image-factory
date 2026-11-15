// Loopback-only real Streamlit measurements; no bootstrap or delivery worker.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true}),report=[];
try {for(const kind of ['abandoned','welcome','post_purchase','win_back','fulfilled','orders_sql'].filter(k=>!process.env.V2_ONLY||k===process.env.V2_ONLY)){
 const samples=[];
 for(let i=0;i<3;i++){
  const p=await browser.newPage({viewport:{width:1440,height:1000}});
  await p.addInitScript(()=>{
   if(window!==top)return;
   window.fixtureCheckReady=()=>{
    const frame=document.querySelector('iframe[title="crm_flow_recipients.crm_checkout_table"]');
    if(window.measureStart&&!window.readyAt&&frame?.checkVisibility()&&frame.contentDocument?.querySelectorAll('tbody tr').length===50)window.readyAt=Date.now();
   };
   addEventListener('message',e=>{if(e.data?.fixtureTableReady)window.fixtureCheckReady()});
   new MutationObserver(()=>window.fixtureCheckReady()).observe(document,{childList:true,subtree:true,attributes:true,attributeFilter:['open','style','hidden']});
  });
  await p.route('**/*',async r=>{
   if(new URL(r.request().url()).hostname!=='127.0.0.1')return r.abort();
   if(r.request().resourceType()==='document'&&r.request().url().includes('crm_checkout_table')){
    const response=await r.fetch();let body=await response.text();
    body=body.replace('function render(){','function render(){const measuredAt=performance.now();')
     .replace('selection();tick(false);height();','selection();tick(false);height();(window.renderSamples??=[]).push(performance.now()-measuredAt);parent.postMessage({fixtureTableReady:Date.now()},"*");');
    return r.fulfill({response,body});
   }return r.continue();
  });
  const nav=Date.now();await p.goto(kind==='orders_sql'?`http://127.0.0.1:${process.env.V2_SQL_PORT||18738}/?profile=1`:`http://127.0.0.1:${process.env.V2_PORT||18749}/?flow=${kind}&profile=1&delay=${process.env.V2_READ_DELAY||.02}`);
  const summary=p.locator('summary').first();await summary.waitFor();
  await p.locator('[data-testid=stApp][data-test-script-state=notRunning]').waitFor();
  const fixtureReadyMs=Date.now()-nav,frame=p.frameLocator('iframe[title="crm_flow_recipients.crm_checkout_table"]'),iframe=p.locator('iframe[title="crm_flow_recipients.crm_checkout_table"]');
  await p.evaluate(()=>{window.measureStart=Date.now();window.readyAt=null});
  const start=Date.now();await summary.click();await iframe.waitFor({state:'visible'});await frame.locator('tbody tr').nth(49).waitFor();const coldMs=Date.now()-start;
  const coldReadyMs=await p.evaluate(()=>window.readyAt-window.measureStart);
  await p.locator('[data-testid=stApp][data-test-script-state=notRunning]').waitFor();await p.waitForTimeout(100);
  const select=Date.now();await frame.locator('tbody input').first().check();assert.equal(await frame.locator('tbody input:checked').count(),1);const selectFeedbackMs=Date.now()-select;
  await p.waitForTimeout(300);await summary.click();await iframe.waitFor({state:'hidden'});await p.waitForTimeout(300);
  await p.evaluate(()=>{window.measureStart=Date.now();window.readyAt=null});
  const warm=Date.now();await summary.click();await iframe.waitFor({state:'visible'});await frame.locator('tbody tr').nth(49).waitFor();const warmMs=Date.now()-warm;
  const warmReadyMs=await p.evaluate(()=>window.readyAt-window.measureStart);
  assert.ok(coldReadyMs>0&&warmReadyMs>0,'Browser readiness observer must record both openings');
  const component=await frame.locator('body').evaluate(()=>window.renderSamples||[]);
  await p.waitForTimeout(1100);
  const metrics=kind==='orders_sql'?JSON.parse(await p.locator('.st-key-fixture-metrics').innerText()):await p.getByText(/^FIXTURE_METRICS/).innerText();
  assert.equal(await p.getByTestId('stException').count(),0);
  samples.push({fixtureReadyMs,coldMs,warmMs,coldReadyMs,warmReadyMs,selectFeedbackMs,component,metrics});await p.close();
 }
 const median=k=>samples.map(x=>x[k]).sort((a,b)=>a-b)[1];
 report.push({kind,coldMs:median('coldMs'),warmMs:median('warmMs'),coldReadyMs:median('coldReadyMs'),warmReadyMs:median('warmReadyMs'),selectFeedbackMs:median('selectFeedbackMs'),samples});
 fs.writeFileSync(`.tmp-email-v2/${process.env.V2_REPORT||'before'}.json`,JSON.stringify(report,null,2));console.log(JSON.stringify(report.at(-1)));
}}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
