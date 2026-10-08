const {chromium}=require('playwright'), fs=require('fs'), assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage(), errors=[];page.on('pageerror',e=>errors.push(e.message));
 const before=process.env.FLOW_BASELINE==='1', result={};
 const at=Date.now();await page.goto((process.env.FLOW_PROFILE_URL||'http://127.0.0.1:8892/')+'?fixture_checkout=1&fixture_analytics=1&fixture_run=compact');
 await page.getByRole('button',{name:'Edit Email',exact:true}).first().waitFor({timeout:30000});result.coldMs=Date.now()-at;
 await page.locator('.sc-flow-thumbnail').first().waitFor();
 async function count(){const prior=await page.locator('#flow-profile').innerText();await page.getByRole('button',{name:'Profile snapshot',exact:true}).click();await page.waitForFunction(old=>document.querySelector('#flow-profile')?.textContent!==old,prior);return JSON.parse(await page.locator('#flow-profile').innerText());}
 async function measure(name,fn){const old=await count();await page.evaluate(()=>{window.flowThumb=document.querySelector('.sc-flow-thumbnail');window.flowFrames=[];window.flowSampling=true;function sample(){if(!window.flowSampling)return;window.flowFrames.push(!!document.querySelector('.sc-flow-thumbnail'));requestAnimationFrame(sample)}sample()});const t=Date.now();await fn();const latest=await count();result[name]={ms:Date.now()-t,queries:latest.queries-old.queries,flowRenders:latest.flow_renders-old.flow_renders,fullRuns:latest.full_runs-old.full_runs,thumbnailRetained:await page.evaluate(()=>window.flowThumb===document.querySelector('.sc-flow-thumbnail')),missingThumbnailFrames:await page.evaluate(()=>{window.flowSampling=false;return window.flowFrames.filter(v=>!v).length})};}
 if(before) await measure('settingsOpen',async()=>{await page.getByText('Trigger and flow settings',{exact:true}).click();await page.getByRole('textbox',{name:'Flow name',exact:true}).waitFor();});
 await measure('settingsEdit',async()=>{await page.getByRole('textbox',{name:'Flow name',exact:true}).fill('Compact fixture');await page.getByRole('textbox',{name:'Flow name',exact:true}).press('Tab');});
 await measure('checkoutsOpen',async()=>{await page.getByText('Abandoned checkouts',{exact:true}).last().click();await page.frameLocator('iframe[title="crm_automation_analytics_ui.crm_checkout_table"]').locator('tbody tr').first().waitFor();});
 await measure('checkoutSearch',async()=>{const input=page.getByRole('textbox',{name:'Search and filter',exact:true});await input.fill('local1@example.test');await input.press('Enter');await page.frameLocator('iframe[title="crm_automation_analytics_ui.crm_checkout_table"]').getByText('Local Collector 1',{exact:true}).first().waitFor();});
 await measure('stepMenu',async()=>{await page.locator('[class*="st-key-flow-row-"]').first().getByRole('button',{name:'⋮',exact:true}).click();await page.getByTestId('stPopoverBody').getByRole('textbox',{name:'Email name',exact:true}).waitFor();});
 await page.keyboard.press('Escape');
 await measure('dateFilter',async()=>{await page.locator('[class*="st-key-auto-analytics-period-"]').getByRole('combobox').click();await page.getByRole('option',{name:'Last 7 days',exact:true}).click();});
 if(!before)await page.locator('.sc-flow-metrics[data-period="Last 7 days"][data-phase="READY"]').first().waitFor();
 await measure('editEmail',async()=>{await page.getByRole('button',{name:'Edit Email',exact:true}).first().click();await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();});
 const back=Date.now();await page.getByRole('button',{name:'Flow',exact:true}).click();await page.getByRole('button',{name:'Edit Email',exact:true}).first().waitFor();result.warmReturnMs=Date.now()-back;
 if(!before){await page.locator('.sc-flow-metrics[data-period="Last 7 days"][data-phase="READY"]').first().waitFor();assert.equal(await page.locator('.sc-flow-metrics').count(),await page.locator('[class*="st-key-flow-row-"]').count());}
 result.final=await count();await page.screenshot({path:'tmp/flow-compact-'+(before?'before':'after')+'.png',fullPage:true});
 if(!before){
  assert.equal(await page.getByText('Performance history',{exact:true}).count(),0);assert.equal(await page.getByText('Recent activity',{exact:true}).count(),0);
  assert.equal(await page.locator('.sc-flow-stats dt').allTextContents().then(x=>x.join('|')),'Entered|Sent|Delivery|Opens|Clicks|Conversions|Orders|Bounce');
  for(const key of ['settingsEdit','checkoutsOpen','checkoutSearch','stepMenu','dateFilter']){assert.equal(result[key].flowRenders,0,key);assert.equal(result[key].fullRuns,0,key);assert.equal(result[key].thumbnailRetained,true,key);}
  // Settings save must refresh the publication toolbar without rebuilding Flow.
  const mark=await count();
  await page.getByRole('textbox',{name:'Flow name',exact:true}).fill('Saved compact fixture');
  await page.getByTestId('stSelectbox').filter({hasText:'Re-entry cooldown'}).getByRole('combobox').click();
  await page.getByRole('option',{name:'7 days',exact:true}).click();
  await page.getByRole('button',{name:'Save flow settings',exact:true}).click();
  await page.locator('.automation-title strong').filter({hasText:'Saved compact fixture'}).waitFor();
  await page.getByRole('button',{name:'Publish changes',exact:true}).waitFor();
  assert.equal((await count()).flow_renders,mark.flow_renders);
  // A settings revision must not invalidate the next email's stable action key.
  await page.locator('[class*="st-key-flow-row-"]').first().getByRole('button',{name:'⋮',exact:true}).click();
  const pop=page.getByTestId('stPopoverBody');
  await pop.getByRole('spinbutton',{name:'Delay',exact:true}).fill('31');
  await pop.getByRole('button',{name:'Save step',exact:true}).click();
  await page.getByText('31 minutes after trigger · Enabled',{exact:true}).waitFor();
  // Search and selections survive a locally closed disclosure.
  const disclosure=page.locator('summary').filter({hasText:'Abandoned checkouts'});
  if(!await page.getByRole('textbox',{name:'Search and filter',exact:true}).isVisible())await disclosure.click();
  const search=page.getByRole('textbox',{name:'Search and filter',exact:true});
  await search.fill('local1@example.test');await search.press('Enter');
  const frame=page.frameLocator('iframe[title="crm_automation_analytics_ui.crm_checkout_table"]');
  await frame.getByRole('checkbox').nth(1).check();
  await page.getByRole('button',{name:'Add to flow',exact:true}).waitFor({state:'visible'});
  await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent==='Add to flow'&&!b.disabled));
  await measure('checkoutsWarmReopen',async()=>{await disclosure.click();await search.waitFor({state:'hidden'});await disclosure.click();await search.waitFor();await frame.getByRole('checkbox').nth(1).waitFor();});
  assert.equal(await search.inputValue(),'local1@example.test');assert.equal(await frame.getByRole('checkbox').nth(1).isChecked(),true);
  await search.fill('');await search.press('Enter');await page.getByRole('button',{name:'Next checkouts',exact:true}).click();
  await page.getByText(/Page 2 ·/).waitFor();await page.getByRole('button',{name:'Previous checkouts',exact:true}).click();await page.getByText(/Page 1 ·/).waitFor();
  assert.ok(await frame.locator('tbody tr').count()<=50);
  await page.getByRole('button',{name:'Refresh analytics',exact:true}).click();
  await page.getByRole('button',{name:'← Automations',exact:true}).click();
  await page.getByText('Recent activity',{exact:true}).waitFor();
 }
 assert.equal(await page.getByTestId('stException').count(),0);assert.deepEqual(errors,[]);
 fs.writeFileSync('tmp/flow-compact-'+(before?'before':'after')+'.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
