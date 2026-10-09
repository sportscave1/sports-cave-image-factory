const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{for(const channel of ['chrome','msedge']){
 const browser=await chromium.launch({channel,headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:950}});
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto('http://127.0.0.1:8544/?fixture_checkout=1&fixture_local_faults=1&fixture_save_delay=1.5&fixture_run='+Date.now());
  await page.getByRole('button',{name:'Edit Email',exact:true}).first().click();await page.getByRole('tab',{name:'Editor',exact:true}).click();
  const controls=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]'),preview=page.locator('.st-key-crm-composer-preview iframe').last().contentFrame();
  await controls.locator('textarea').first().waitFor();
  await controls.locator('body').evaluate(()=>{window.lastServerArgs=null;addEventListener('message',e=>{if(e.data.type==='streamlit:render')window.lastServerArgs=structuredClone(e.data.args)});});
  await controls.locator('textarea').first().fill('<p>First draft edit</p>');
  await preview.getByText('First draft edit',{exact:true}).waitFor({timeout:500});
  await controls.getByText(/^Save failed ·/).waitFor({timeout:10000});
  await controls.locator('textarea').first().fill('<p>Newer edit during retry</p>');
  await preview.getByText('Newer edit during retry',{exact:true}).waitFor({timeout:500});
  await controls.getByRole('button',{name:'Duplicate section',exact:true}).first().click();
  await controls.getByRole('button',{name:'Visible section — click to hide'}).first().click();
  assert.equal(await preview.getByText('Newer edit during retry',{exact:true}).count(),1);
  // Re-deliver an older render while a newer local generation is outstanding.
  await controls.locator('body').evaluate(()=>{if(!window.lastServerArgs)throw Error('Missing captured response');dispatchEvent(new MessageEvent('message',{source:parent,data:{type:'streamlit:render',args:window.lastServerArgs}}));});
  assert.equal(await preview.getByText('Newer edit during retry',{exact:true}).count(),1);
  await controls.getByText('Saved · Draft',{exact:true}).waitFor({timeout:15000});
  const expected=await controls.locator('.section').evaluateAll(ns=>ns.map(n=>({id:n.dataset.id,hidden:n.classList.contains('is-hidden')})));
  await page.getByRole('button',{name:'Flow',exact:true}).click();await page.getByRole('button',{name:'Edit Email',exact:true}).first().click();await page.getByRole('tab',{name:'Editor',exact:true}).click();
  await controls.locator('.section').first().waitFor();
  assert.deepEqual(await controls.locator('.section').evaluateAll(ns=>ns.map(n=>({id:n.dataset.id,hidden:n.classList.contains('is-hidden')}))),expected);
  await preview.getByText('Newer edit during retry',{exact:true}).waitFor();
  assert.equal(await page.getByTestId('stException').count(),0);console.log(channel+': failed save, delayed retry, rapid edits, stale response and reopen passed');
 }finally{await browser.close();}
}})().catch(e=>{console.error(e);process.exit(1)});
