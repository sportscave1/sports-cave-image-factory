const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
const browser=await chromium.launch({channel:'chrome',headless:true});
try {
for (const [action,scenario] of [['Close','success'],['New Campaign','success'],['Close','failure']]) {
const page=await browser.newPage({viewport:{width:1280,height:900}});
await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
await page.goto((process.env.POSTING_FIXTURE_URL||'http://127.0.0.1:8896')+'/?scenario='+scenario);
await page.getByRole('button',{name:'Start mocked upload'}).click();
const dialog=page.getByRole('dialog');
await dialog.waitFor();
await page.evaluate(()=>{
 window.popup=document.querySelector('[role=dialog]');
 window.popupRemoved=false;window.maxDialogs=1;
 window.popupWatch=new MutationObserver(()=>{
   window.popupRemoved ||= !window.popup.isConnected;
   window.maxDialogs=Math.max(window.maxDialogs,document.querySelectorAll('[role=dialog]').length);
 });
 window.popupWatch.observe(document.body,{childList:true,subtree:true});
});
await dialog.getByText('final verification pending',{exact:false}).waitFor();
const fill=dialog.locator('[role="progressbar"] > div > div');
assert.equal(await fill.evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(212, 165, 76)');
if(scenario==='failure') {
 await dialog.getByRole('button',{name:'Retry incomplete steps'}).waitFor({timeout:15000});
 await dialog.getByText('Mock upload failed',{exact:true}).waitFor();
 await dialog.getByRole('button',{name:'Retry incomplete steps'}).click();
 // Retry deliberately restarts the same failed job's status view.
 await page.evaluate(()=>{window.popup=document.querySelector('[role=dialog]');window.popupRemoved=false;});
}
await dialog.getByText('3 of 3 ads verified',{exact:true}).waitFor({timeout:20000});
assert.equal(await fill.evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(212, 165, 76)');
assert.equal(await dialog.locator('.posting-success').evaluate(e=>getComputedStyle(e).color),'rgb(22, 131, 66)');
await page.waitForTimeout(2400);
assert.deepEqual(await page.evaluate(()=>({removed:window.popupRemoved,max:window.maxDialogs})),{removed:false,max:1});
await dialog.getByRole('button',{name:action,exact:true}).click();
await dialog.waitFor({state:'hidden',timeout:4000});
await page.getByRole('textbox',{name:'Campaign form'}).fill('Underlying form usable');
await page.waitForTimeout(2400);
assert.equal(await dialog.count(),0);
await page.getByText('Starts: 1',{exact:true}).waitFor();
await page.getByText('Retries: '+(scenario==='failure'?1:0),{exact:true}).waitFor();
const reads=await page.getByText(/^Reads: /).textContent();
await page.getByRole('textbox',{name:'Campaign form'}).press('Enter');
assert.equal(await page.getByText(/^Reads: /).textContent(),reads);
assert.equal(new URL(page.url()).searchParams.has('meta_posting_job'),false);
assert.equal(await page.locator('[data-testid="stException"]').count(),0);
await page.reload();
await page.getByRole('button',{name:'Start mocked upload'}).waitFor();
assert.equal(await dialog.count(),0);
console.log(JSON.stringify({action,scenario,stableDialog:true,goldProgress:true,underlyingClickable:true,noReopen:true}));
await page.close();
}
} finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
