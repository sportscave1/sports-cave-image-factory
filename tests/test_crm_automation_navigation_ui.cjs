// Synthetic loopback data only. Sample every painted frame through navigation.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.NAV_URL||'http://127.0.0.1:8540/';
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const results=[];
 for(const scenario of ['cold','warm','slow']){
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  if(scenario==='slow'){const cdp=await context.newCDPSession(page);await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:150,downloadThroughput:200000,uploadThroughput:100000});}
  await page.goto(base+'?fixture_run=navigation');
  const actions=page.locator('[class*="st-key-auto_actions_"] button').first();await actions.waitFor();
  async function open(){
   await actions.click();const button=page.getByRole('button',{name:'Open editor',exact:true});await button.waitFor();
   await page.evaluate(()=>{window.navFrames=[];window.navStart=performance.now();window.navSampling=true;function frame(){if(!window.navSampling)return;const editor=document.querySelector('.st-key-crm-automation-editor');const home=document.querySelector('.sc-auto-kpis');let faded=false;for(let n=editor;n;n=n.parentElement){const opacity=Number(getComputedStyle(n).opacity);if(opacity>0&&opacity<0.99)faded=true;}const icons=[...document.querySelectorAll('.sc-home-icon img')];window.navFrames.push({ms:performance.now()-window.navStart,editor:!!editor,toolbar:!!document.querySelector('.automation-title'),home:!!home,faded,giant:icons.some(i=>i.getBoundingClientRect().width>40)});requestAnimationFrame(frame)}requestAnimationFrame(frame)});
   await button.click();await page.locator('.automation-title').waitFor();await page.getByRole('button',{name:'Edit email',exact:true}).first().waitFor();
   await page.waitForTimeout(300);
   return await page.evaluate(()=>{window.navSampling=false;return window.navFrames});
  }
  if(scenario==='warm'){await open();await page.getByRole('button',{name:'← Automations',exact:true}).click();await actions.waitFor();}
  const frames=await open();
  const report={scenario,toolbarMs:Math.round(frames.find(f=>f.toolbar)?.ms||0),overlapFrames:frames.filter(f=>f.editor&&f.home).length,giantFrames:frames.filter(f=>f.giant).length,fadedFrames:frames.filter(f=>f.faded).length,errors};results.push(report);
  await page.screenshot({path:`tmp/navigation-${process.env.NAV_BASELINE?'before':'after'}-${scenario}.png`});
  if(!process.env.NAV_BASELINE){
   assert.equal(report.overlapFrames,0);assert.equal(report.giantFrames,0);assert.equal(report.fadedFrames,0);assert.deepEqual(errors,[]);assert.equal(await page.locator('.sc-auto-kpi').count(),0);
   if(scenario==='cold'&&!process.env.NAV_MEASURE_ONLY){
    await page.getByRole('button',{name:'Edit email',exact:true}).first().click();
    await page.locator('.st-key-crm-composer-preview iframe').waitFor();
    for(const tab of ['Editor','Templates','Settings']){await page.getByRole('tab',{name:tab,exact:true}).click();assert.equal(await page.getByTestId('stException').count(),0);}
    for(const width of [1000,750,390,320]){await page.setViewportSize({width,height:1000});assert.equal(await page.locator('.st-key-automation-toolbar').evaluate(e=>e.scrollWidth>e.clientWidth+2),false);}
    await page.setViewportSize({width:1440,height:1000});
    await page.getByRole('button',{name:'Flow Builder',exact:true}).click();
    await page.getByRole('button',{name:'Edit email',exact:true}).nth(1).click();
    await page.locator('.st-key-crm-composer-preview iframe').waitFor();
    await page.reload();await page.getByRole('button',{name:'Edit email',exact:true}).first().waitFor();
    assert.equal(await page.locator('.sc-auto-kpi').count(),0);
    await page.getByRole('button',{name:'← Automations',exact:true}).click();await actions.waitFor();
    assert.equal(await page.locator('.sc-auto-kpi').count(),6);
    await page.locator('[class*="st-key-auto_actions_"] button[data-testid="stPopoverButton"]:visible').nth(1).click();
    await page.getByRole('button',{name:'Open editor',exact:true}).evaluate(b=>{b.click();b.click()});
    await page.getByRole('button',{name:'Edit email',exact:true}).first().waitFor();
    assert.equal(await page.locator('.st-key-crm-automation-editor').count(),1);
    assert.equal(await page.getByTestId('stException').count(),0);
   }
  }
  await context.close();
 }
 if(!process.env.NAV_BASELINE&&!process.env.NAV_MEASURE_ONLY){
  for(const kind of ['delay','failure']){
   const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());const page=await context.newPage();
   await page.goto(`${base}?fixture_toolbar_live=1&fixture_run=navigation&fixture_navigation_${kind}=1`);
   if(kind==='delay'){
    await page.getByText('Opening automation…',{exact:true}).waitFor();
    assert.equal(await page.locator('.sc-auto-kpi').count(),0);await page.screenshot({path:'tmp/navigation-loading.png'});
   }else{
    await page.getByText('Synthetic editor read unavailable',{exact:true}).waitFor();
    await page.screenshot({path:'tmp/navigation-retry.png'});
    await page.getByRole('button',{name:'Retry opening editor',exact:true}).click();
   }
   await page.getByRole('button',{name:'Edit email',exact:true}).first().waitFor();
   assert.equal(await page.locator('.sc-auto-kpi').count(),0);assert.equal(await page.getByTestId('stException').count(),0);await context.close();
  }
 }
 fs.writeFileSync(`tmp/navigation-${process.env.NAV_BASELINE?'before':'after'}.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
