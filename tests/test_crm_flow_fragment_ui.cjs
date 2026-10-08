// Disposable SQL fixture only; all non-loopback browser traffic is blocked.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const base=process.env.FLOW_URL||'http://127.0.0.1:8893/';
 const start=Date.now();await page.goto(base+'?fixture_toolbar_live=1&fixture_run=fragment'+Date.now());
 const rows=page.locator('[class*="st-key-flow-row-"]');
 await rows.nth(1).waitFor();await page.locator('.sc-flow-metrics[data-phase="READY"]').first().waitFor();
 const initialMs=Date.now()-start;
 async function closeMenu(){await page.locator('.sc-flow-stats').click();await page.waitForFunction(()=>[...document.querySelectorAll('[data-testid="stPopoverBody"]')].every(e=>!e.getClientRects().length));}
 async function move(index,action){await closeMenu();await rows.nth(index).getByRole('button',{name:'⋮',exact:true}).click();await page.locator('[data-testid="stPopoverBody"]:visible').getByRole('button',{name:action,exact:true}).click();}
 const original=await rows.first().getAttribute('class'),t=Date.now();
 await move(0,'Move down');
 await page.waitForFunction(c=>document.querySelectorAll('[class*="st-key-flow-row-"]')[1]?.className===c,original);
 await page.locator('.sc-flow-metrics[data-phase="READY"]').nth(1).waitFor();
 const reorderMs=Date.now()-t;
 assert.equal(await page.getByTestId('stException').count(),0);
 for(let i=0;i<3;i++){await move(1,'Move up');await page.waitForFunction(c=>document.querySelector('[class*="st-key-flow-row-"]')?.className===c,original);await move(0,'Move down');await page.waitForFunction(c=>document.querySelectorAll('[class*="st-key-flow-row-"]')[1]?.className===c,original);}
 await closeMenu();await page.getByRole('button',{name:'Refresh analytics',exact:true}).click();
 await page.locator('.sc-flow-metrics[data-phase="READY"]').nth(1).waitFor();
 await page.reload();await rows.nth(1).waitFor();assert.equal(await rows.nth(1).getAttribute('class'),original);
 await page.getByRole('button',{name:'Publish changes',exact:true}).waitFor();
 await page.getByRole('button',{name:'Pause',exact:true}).click();
 await page.getByRole('button',{name:'Resume',exact:true}).waitFor().catch(async e=>{console.error(await page.locator('.st-key-flow-workspace').innerText());throw e;});
 await page.getByRole('button',{name:'Resume',exact:true}).click();
 await page.getByRole('button',{name:'Pause',exact:true}).waitFor();
 await page.getByRole('button',{name:'Test',exact:true}).click();
 await page.getByText(/Simulation only. No customer emails/).waitFor();
 await closeMenu();
 await page.getByRole('button',{name:'+ Add Email',exact:true}).click();await rows.nth(2).waitFor();
 await page.locator('.sc-flow-metrics[data-phase="READY"]').nth(2).waitFor();
 assert.equal(await page.locator('.sc-flow-metrics').count(),3);
 assert.equal(await page.getByTestId('stException').count(),0);assert.deepEqual(errors,[]);
 console.log(JSON.stringify({result:'PASS initial render, repeated live-flow draft reorder, metrics refresh, reload persistence, add email',initialMs,reorderMs}));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
