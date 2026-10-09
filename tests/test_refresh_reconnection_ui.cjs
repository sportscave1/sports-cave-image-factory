// Reproduce the old shared reload on a real edited Refresh page, then verify protection.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),cp=require('node:child_process');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});
try{for(const baseline of [true,false]){
 const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage();page.setDefaultTimeout(15000);
 await page.goto('http://127.0.0.1:8557/?format=Carousel&count=4&draft=1');
 const input=page.getByRole('textbox',{name:'Card 1 headline',exact:true});await input.fill('Unsaved reconnect draft');await input.press('Tab');
 const source=baseline?cp.execFileSync('git',['show','HEAD:components/session_recovery.js'],{encoding:'utf8'}):fs.readFileSync('components/session_recovery.js','utf8');
 await page.addScriptTag({content:source});
 await page.evaluate(()=>{const fake=document.createElement('div');fake.id='fixture-disconnect';fake.innerHTML='<div data-testid="stSidebar"><button disabled>Connection unavailable</button></div><div role="dialog"><h2>Connection error</h2></div>';document.body.append(fake);});
 if(baseline){await page.waitForEvent('framenavigated',{predicate:f=>f===page.mainFrame()});await input.waitFor();assert.notEqual(await input.inputValue(),'Unsaved reconnect draft');}
 else{
  await page.getByText(/Automatic page reload is paused to protect your draft/).waitFor();
  await page.waitForTimeout(4000);assert.equal(await input.inputValue(),'Unsaved reconnect draft');
  await page.evaluate(()=>document.getElementById('fixture-disconnect').remove());
  await input.fill('Recovered edit');await input.press('Tab');assert.equal(await input.inputValue(),'Recovered edit');
 }
 await context.close();console.log(baseline?'Reproduced: legacy health recovery reload loses unsaved copy':'Verified: Refresh stays open, explains interruption, and resumes editing without data loss');
}}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
