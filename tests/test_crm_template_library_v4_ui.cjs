// Existing synthetic automation fixture, loopback only. No real providers.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const panel=page.locator('.st-key-crm-composer-controls');const library=page.locator('.st-key-crm-compact-library');
 const name='V4 reusable '+Date.now();const original='<table role="presentation"><tr><td><p style="color:#123456">Original {{ first_name }}</p></td></tr></table><!-- untouched source -->';
 const tab=label=>page.getByRole('tab',{name:label,exact:true});
 const groups=()=>library.locator('[class*="st-key-compact-group-"] button');
 const select=async(label,value)=>{await page.getByTestId('stSelectbox').filter({has:page.getByText(label,{exact:true})}).getByRole('combobox').click();await page.getByRole('option',{name:value,exact:true}).click();};
 const waitSource=expected=>page.waitForFunction(v=>[...document.querySelectorAll('textarea')].some(e=>e.value===v),expected);
 const valueIs=async(locator,value)=>{for(let i=0;i<100;i++){if(await locator.inputValue()===value)return;await page.waitForTimeout(30);}assert.equal(await locator.inputValue(),value);};
 const runs=()=>page.locator('#inline-full-runs').getAttribute('data-runs');
 try{
  await page.goto((process.env.FLOW_URL||'http://127.0.0.1:18606/')+'?fixture_existing=post_purchase&fixture_inline=1&fixture_run='+name);
  await page.getByRole('button',{name:/Edit Email/}).first().click();
  await page.getByText('Flow email',{exact:true}).waitFor();
  await page.waitForTimeout(350); // Allow the initial editor mount/toolbar acknowledgement to settle.
  const subject=page.getByRole('textbox',{name:'Subject',exact:true});await subject.fill('V4 independent subject');await subject.press('Tab');
  await page.waitForTimeout(350); // Native field persistence completes before changing the tab.
  await tab('Templates').click();await library.waitFor();const full=await runs();
  assert.equal(await library.getByRole('button',{name:'Use',exact:true}).count(),0);
  assert.equal(await library.locator('[class*="st-key-compact-row-"]').count(),0);
  const start=Date.now();await library.getByRole('button',{name:/Defaults/}).click();
  await library.getByRole('button',{name:/Edit Footer/}).waitFor();
  const groupMs=Date.now()-start;assert.equal(await runs(),full);
  await library.getByRole('button',{name:/Edit Footer/}).click();
  const footer=page.getByRole('textbox',{name:'HTML source',exact:true});await footer.waitFor();const protectedSource=await footer.inputValue();
  await footer.fill('<p>Missing unsubscribe</p>');await page.getByRole('button',{name:'Save template',exact:true}).click();
  await page.getByText('Default footer must include a visible {{UNSUBSCRIBE_URL}} link.',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Cancel',exact:true}).click();
  await library.getByRole('button',{name:/Edit Footer/}).click();await waitSource(protectedSource);assert.equal(await footer.inputValue(),protectedSource);
  await page.getByRole('button',{name:'Cancel',exact:true}).click();
  await library.getByRole('button',{name:/Add template/}).click();
  await page.getByRole('textbox',{name:'Template name',exact:true}).fill(name);await select('Group','Post Purchase');
  await page.getByRole('textbox',{name:'HTML source',exact:true}).fill(original);await page.getByRole('button',{name:'Save template',exact:true}).click();
  await library.getByRole('button',{name:/Post Purchase/}).click();
  await library.getByRole('button',{name:new RegExp('Edit '+name)}).waitFor();
  await library.getByRole('button',{name:new RegExp('Edit '+name)}).click();await waitSource(original);assert.equal(await page.getByRole('textbox',{name:'HTML source',exact:true}).inputValue(),original);
  await page.getByRole('button',{name:'Cancel',exact:true}).click();assert.equal(await runs(),full,'library actions never reload workspace');
  console.log('Library create/save/default protection passed');
  await tab('Editor').click();
  const frame=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]');
  await frame.locator('#add summary').click();await frame.getByRole('button',{name:'Apply '+name,exact:true}).click();
  const area=frame.getByRole('textbox',{name:/HTML Section.*HTML/}).first();await area.waitFor();
  await page.waitForFunction(()=>{const f=document.querySelector('iframe[title="crm_section_ui.crm_middle_sections_v2"]');return f?.contentDocument?.querySelector('textarea')?.value.includes('untouched source');});
  assert.equal(await area.inputValue(),original);
  const customised=original.replace('Original','Customised')+'<style>@media(max-width:600px){p{font-size:12px}}</style>';
  await area.fill(customised);await area.press('Tab');
  await tab('Settings').click();await valueIs(subject,'V4 independent subject');
  await tab('Templates').click();await library.getByRole('button',{name:new RegExp('Edit '+name)}).click();
  const source=page.getByRole('textbox',{name:'HTML source',exact:true});await waitSource(original);assert.equal(await source.inputValue(),original);
  await source.fill('<p>Library changed</p>');await page.getByRole('button',{name:'Save template',exact:true}).click();
  await tab('Editor').click();await area.waitFor();await valueIs(area,customised);
  await area.fill(customised+'<!-- unsaved -->');
  await frame.locator('#add summary').click();page.once('dialog',d=>d.dismiss());await frame.getByRole('button',{name:'Apply '+name,exact:true}).click();
  assert.equal(await area.inputValue(),customised+'<!-- unsaved -->','cancel replacement retains edits');
  page.once('dialog',d=>d.accept());await frame.getByRole('button',{name:'Apply '+name,exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('iframe[title="crm_section_ui.crm_middle_sections_v2"]')?.contentDocument?.querySelector('textarea')?.value==='<p>Library changed</p>');
  await tab('Settings').click();await valueIs(subject,'V4 independent subject');
  console.log('Independent source edits and replacement passed');
  // Settings and large source panels share one left scroll container.
  for(const width of [1440,1024,750,390,320]){
   await page.setViewportSize({width,height:850});await tab('Settings').click();
   await panel.evaluate(e=>{e.scrollTop=0;});const before=await tab('Settings').boundingBox();
   await panel.evaluate(e=>{e.scrollTop=e.scrollHeight;});const after=await tab('Settings').boundingBox();
   assert.ok(Math.abs(before.y-after.y)<3,'tabs stay within panel at '+width+': '+JSON.stringify({before,after}));
   assert.equal(await page.getByTestId('stMain').evaluate(e=>e.scrollWidth>e.clientWidth+2),false,'responsive overflow '+width);
   await tab('Templates').click();await library.getByRole('button',{name:/Defaults/}).waitFor();
   await panel.evaluate(e=>{e.scrollTop=0;});await page.screenshot({path:'.tmp-editor-v4/library-'+width+'.png'});
  }
  await page.setViewportSize({width:1440,height:1000});await tab('Editor').click();
  await page.getByText('Personalise Image',{exact:true}).click();
  await page.getByTestId('stSelectbox').filter({has:page.getByText('Source',{exact:true})}).getByRole('combobox').waitFor();
  const imageBox=await page.locator('.st-key-crm-personalise-image').boundingBox();const panelBox=await panel.boundingBox();assert.ok(imageBox.x+imageBox.width<=panelBox.x+panelBox.width+2);
  await select('Source','Actual Purchased Product');await page.getByRole('button',{name:'Apply image settings',exact:true}).click();
  await frame.getByRole('button',{name:'Edit Personalised artwork',exact:true}).waitFor();
  await page.getByRole('button',{name:'Flow',exact:true}).click();
  await page.getByRole('button',{name:/Edit Email/}).first().waitFor();await page.reload();
  await page.getByRole('button',{name:/Edit Email/}).first().click();
  await tab('Editor').click();await frame.getByRole('button',{name:'Edit Personalised artwork',exact:true}).waitFor();
  assert.equal(await area.inputValue(),'<p>Library changed</p>','saved draft survives reopening');
  await page.locator('[class*="device_Mobile"] button').first().click();
  await page.locator('[class*="device_Desktop"] button').first().click();
  assert.equal(errors.length,0,errors.join('\n'));
  fs.writeFileSync('.tmp-editor-v4/browser-results.json',JSON.stringify({passed:true,groupMs,widths:[1440,1024,750,390,320],errors},null,2));
  console.log('PASS compact template library, independent HTML copies, confirmation, defaults, sticky tabs, responsive preview and personalised image; group '+groupMs+'ms');
 }catch(error){console.log(await page.locator('body').innerText());await page.screenshot({path:'.tmp-editor-v4/failure.png'});throw error;}
 finally{await browser.close();}
})();
