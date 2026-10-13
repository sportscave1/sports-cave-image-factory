// Actual shared table in Chromium, synthetic projections, network blocked.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage();await page.route('**/*',r=>r.abort());
 await page.setContent('<iframe style="width:100%;height:720px;border:0"></iframe>');
 await page.evaluate(source=>document.querySelector('iframe').srcdoc=source,fs.readFileSync('components/crm_checkout_table/index.html','utf8'));
 const frame=page.frameLocator('iframe');await frame.locator('#root').waitFor({state:'attached'});
 const stamp='2026-10-13T00:25:03Z',label='Purchased — reminders stopped';
 const payload={columns:[{id:'step',label:'Email 1',enabled:true}],rows:[{key:'synthetic',customer:'Fixture Collector',
   created:'13 Oct · 9:25 am',created_full:'13 Oct 2026 09:25:03 AEDT',cells:[{label,tone:'muted',reason:'Verified newer paid order'}]}],
   selected:[],server_now:stamp,read_at:stamp,phase:'READY',refresh_seconds:0};
 await page.evaluate(args=>document.querySelector('iframe').contentWindow.postMessage({type:'streamlit:render',args},'*'),payload);
 await frame.locator('tbody tr').waitFor();
 for(const width of [1366,390,320]){
   await page.setViewportSize({width,height:850});
   assert.equal(await frame.locator('tbody td').nth(2).textContent(),'13 Oct · 9:25 am');
   assert.equal(await frame.locator('tbody td').nth(3).textContent(),label);
   await frame.locator('body').evaluate(()=>tick(false));
   assert.equal(await frame.locator('tbody td').nth(3).textContent(),label,'purchase does not revert to Due on ticking');
   assert.equal(await frame.locator('body').evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth),false);
 }
 console.log('PASS: abandonment date/time and purchased exit remain visible through desktop/mobile ticking; no document overflow.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
