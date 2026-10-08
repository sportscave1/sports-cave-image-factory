const {chromium}=require('playwright'), fs=require('fs'), assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage(), errors=[];page.on('pageerror',e=>errors.push(e.message));
 const before=process.env.FLOW_BASELINE==='1', result={};
 const at=Date.now();await page.goto('http://127.0.0.1:8892/?fixture_checkout=1&fixture_analytics=1&fixture_run=compact');
 await page.getByRole('button',{name:'Edit Email',exact:true}).first().waitFor({timeout:30000});result.coldMs=Date.now()-at;
 await page.locator('.sc-flow-thumbnail').first().waitFor();
 async function count(){const prior=await page.locator('#flow-profile').innerText();await page.getByRole('button',{name:'Profile snapshot',exact:true}).click();await page.waitForFunction(old=>document.querySelector('#flow-profile')?.textContent!==old,prior);return JSON.parse(await page.locator('#flow-profile').innerText());}
 async function measure(name,fn){const old=await count();await page.evaluate(()=>window.flowThumb=document.querySelector('.sc-flow-thumbnail'));const t=Date.now();await fn();const latest=await count();result[name]={ms:Date.now()-t,queries:latest.queries-old.queries,flowRenders:latest.flow_renders-old.flow_renders,fullRuns:latest.full_runs-old.full_runs,thumbnailRetained:await page.evaluate(()=>window.flowThumb===document.querySelector('.sc-flow-thumbnail'))};}
 if(before) await measure('settingsOpen',async()=>{await page.getByText('Trigger and flow settings',{exact:true}).click();await page.getByRole('textbox',{name:'Flow name',exact:true}).waitFor();});
 await measure('settingsEdit',async()=>{await page.getByRole('textbox',{name:'Flow name',exact:true}).fill('Compact fixture');await page.getByRole('textbox',{name:'Flow name',exact:true}).press('Tab');});
 await measure('checkoutsOpen',async()=>{await page.getByText('Abandoned checkouts',{exact:true}).last().click();await page.frameLocator('iframe[title="crm_automation_analytics_ui.crm_checkout_table"]').locator('tbody tr').first().waitFor();});
 await measure('checkoutSearch',async()=>{const input=page.getByRole('textbox',{name:'Search and filter',exact:true});await input.fill('local1@example.test');await input.press('Enter');await page.frameLocator('iframe[title="crm_automation_analytics_ui.crm_checkout_table"]').getByText('Local Collector 1',{exact:true}).waitFor();});
 await measure('stepMenu',async()=>{await page.locator('[class*="st-key-flow-row-"]').first().getByRole('button',{name:'⋮',exact:true}).click();await page.getByTestId('stPopoverBody').getByRole('textbox',{name:'Email name',exact:true}).waitFor();});
 await page.keyboard.press('Escape');
 await measure('editEmail',async()=>{await page.getByRole('button',{name:'Edit Email',exact:true}).first().click();await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();});
 const back=Date.now();await page.getByRole('button',{name:'Flow',exact:true}).click();await page.getByRole('button',{name:'Edit Email',exact:true}).first().waitFor();result.warmReturnMs=Date.now()-back;
 result.final=await count();await page.screenshot({path:'tmp/flow-compact-'+(before?'before':'after')+'.png',fullPage:true});
 if(!before){
  assert.equal(await page.getByText('Performance history',{exact:true}).count(),0);assert.equal(await page.getByText('Recent activity',{exact:true}).count(),0);
  assert.equal(await page.locator('.sc-flow-stats dt').allTextContents().then(x=>x.join('|')),'Entered|Sent|Delivery|Opens|Clicks|Conversions|Orders|Bounce');
  for(const key of ['settingsEdit','checkoutsOpen','checkoutSearch','stepMenu']){assert.equal(result[key].flowRenders,0,key);assert.equal(result[key].fullRuns,0,key);assert.equal(result[key].thumbnailRetained,true,key);}
 }
 assert.equal(await page.getByTestId('stException').count(),0);assert.deepEqual(errors,[]);
 fs.writeFileSync('tmp/flow-compact-'+(before?'before':'after')+'.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
