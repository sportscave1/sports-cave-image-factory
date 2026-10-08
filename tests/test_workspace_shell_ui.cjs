const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.route('**/*',r=>{
  const u=new URL(r.request().url());
  if(u.hostname!=='127.0.0.1')return r.abort();
  if(u.pathname.startsWith('/api/')||u.port==='1')return r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({notifications:[],action_required_count:0,unread_count:0,timer:{},events:[]})});
  return r.continue();
 });
 const page=await context.newPage();page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8552/');await page.locator('#sports-cave-os-top-bar').waitFor();await page.locator('#shell-fixture-runs').waitFor();
 await page.waitForFunction(()=>window.SportsCaveSessionRecovery?.version===2);
 await page.evaluate(()=>{window.originalShell=document.getElementById('sports-cave-os-top-bar');window.originalRecovery=window.SportsCaveSessionRecovery;});
 for(let i=0;i<8;i++){
  const prior=await page.locator('#shell-fixture-runs').innerText();await page.getByRole('button',{name:'Local shell rerun',exact:true}).click();
  await page.waitForFunction(old=>document.querySelector('#shell-fixture-runs')?.textContent!==old,prior);
  assert.equal(await page.evaluate(()=>window.originalShell===document.getElementById('sports-cave-os-top-bar')),true);
  assert.equal(await page.evaluate(()=>window.originalRecovery===window.SportsCaveSessionRecovery),true);
 }
 assert.equal(await page.locator('#sports-cave-os-top-bar').count(),1);assert.equal(await page.getByTestId('stException').count(),0);
 fs.mkdirSync('.tmp-performance-results',{recursive:true});await page.screenshot({path:'.tmp-performance-results/shell-desktop.png'});
 await page.setViewportSize({width:650,height:850});await page.getByRole('button',{name:'Local shell rerun',exact:true}).click();await page.locator('#shell-fixture-runs').waitFor();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
 assert.deepEqual(errors,[]);console.log('PASS: eight shell reruns preserve one header and recovery observer, no JavaScript/Streamlit errors, desktop and narrow viewport.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
