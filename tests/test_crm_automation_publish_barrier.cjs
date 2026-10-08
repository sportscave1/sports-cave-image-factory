const {chromium}=require('playwright'),fs=require('fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage();page.setDefaultTimeout(5000);
  await page.setContent('<div class="st-key-crm-automation-editor"><div class="st-key-automation-toolbar"><div><button>Publish changes</button></div></div><div class="st-key-crm-composer-controls"></div><div id="preview"></div></div>');
  await page.evaluate(()=>{window.submissions=0;document.querySelector('button').onclick=()=>submissions++;window.scCampaignFlushSections=()=>Promise.resolve();});
  await page.addScriptTag({content:fs.readFileSync('components/crm_sections/automation_publish.js','utf8')});
  // Continuous unrelated preview work must not delay a saved draft request.
  await page.evaluate(()=>{window.animation=setInterval(()=>document.querySelector('#preview').textContent=Date.now(),10);});
  await page.getByRole('button',{name:'Publish changes',exact:true}).click();
  await page.waitForFunction(()=>submissions===1);
  // A pending save acknowledgement gates dispatch, including double clicks.
  await page.evaluate(()=>{window.scCampaignFlushSections=()=>new Promise(resolve=>window.release=resolve);});
  await page.getByRole('button',{name:'Publish changes',exact:true}).dblclick();
  assert.equal(await page.evaluate(()=>submissions),1);
  await page.evaluate(()=>release());await page.waitForFunction(()=>submissions===2);
  // Failed/timed-out save acknowledgement never publishes and permits retry.
  await page.evaluate(()=>{window.scCampaignFlushSections=()=>Promise.reject(new Error('Save timed out'));});
  await page.getByRole('button',{name:'Publish changes',exact:true}).click();
  await page.getByText('Save your latest edits, then retry publishing.',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>submissions),2);
  await page.evaluate(()=>{window.scCampaignFlushSections=()=>Promise.resolve();document.querySelector('button').textContent='Retry Publish';});
  await page.getByRole('button',{name:'Retry Publish',exact:true}).click();await page.waitForFunction(()=>submissions===3);
  console.log('PASS publish save barrier: unrelated preview mutations, acknowledgement, duplicate clicks, timeout rejection, retry');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
