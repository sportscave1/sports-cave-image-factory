// Local actual Campaign/Automation editor interaction contract.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});const results=[];
try{for(const kind of ['automation','campaign']){
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(20000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 try{
 if(kind==='automation'){await page.goto('http://127.0.0.1:18895/?fixture_checkout=1&fixture_click_edit=1&fixture_run=click-'+Date.now());await page.getByRole('button',{name:/Edit Email/}).first().click();}
 else{await page.goto('http://127.0.0.1:18894');await page.getByRole('link',{name:'Open Catalogue fixture',exact:true}).click();}
 const tab=n=>page.getByRole('tab',{name:n,exact:true});const editor=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]'),preview=()=>page.frameLocator('.st-key-crm-composer-preview iframe');
 await tab('Editor').click();await editor.locator('.section').first().waitFor();
 const read=()=>editor.locator('body').evaluate(()=>structuredClone([...parent.scEmailDrafts.values()].find(s=>s.sections?.some(p=>p.id===document.querySelector('.section')?.dataset.id)).sections));
 const add=async type=>{await editor.locator('#add>summary').click();await editor.locator(`[data-add="${type}"]`).click();return (await read()).at(-1);};
 const html=await add('html');const source='<table role="presentation"><tr><td><p>Nested <strong>Click text</strong></p><a href="https://www.sportscaveshop.com/products/fixture"><img src="https://cdn.shopify.com/s/files/fixture.png" width="100" height="80" alt="Clickable artwork">Preview CTA</a><div>10% discount box</div></td></tr></table>';
 await editor.locator(`[data-id="${html.id}"] textarea:not([readonly])`).fill(source);await editor.locator(`[data-id="${html.id}"] textarea:not([readonly])`).press('Tab');
 const button=await add('button'),image=await add('image');await editor.locator(`[data-id="${image.id}"] textarea:not([readonly])`).fill('<img src="https://cdn.shopify.com/s/files/banner.png" width="100" height="80" alt="Clickable banner">');await editor.locator(`[data-id="${image.id}"] textarea:not([readonly])`).press('Tab');
 await editor.locator(`[data-id="${html.id}"]`).getByRole('button',{name:'Duplicate section',exact:true}).click();let sections=await read();const duplicate=sections[sections.findIndex(s=>s.id===html.id)+1];
 const handle=editor.locator(`[data-id="${duplicate.id}"] [data-drag]`).first();await handle.focus();await page.keyboard.press('Alt+ArrowUp');
 // A real catalogue in the campaign exercises nested title/artwork/CTA targets.
 if(kind==='campaign'){
  if(!(await read()).some(s=>s.type==='catalogue'))await add('catalogue');
  const cat=(await read()).find(s=>s.type==='catalogue');const card=editor.locator(`[data-id="${cat.id}"]`);if(await card.locator('.title').getAttribute('aria-expanded')!=='true')await card.locator('.title').click();
  const smart=card.getByRole('checkbox',{name:'Smart recommendations'});if(await smart.isChecked())await smart.uncheck();await card.getByRole('button',{name:/Select products/}).click();const dialog=page.getByRole('dialog');const checkbox=dialog.getByRole('checkbox',{name:'Select Artwork 2',exact:true});if(!await checkbox.isChecked())await dialog.locator('label').filter({has:page.getByRole('checkbox',{name:'Select Artwork 2',exact:true})}).click();await dialog.getByRole('button',{name:'Add selected',exact:true}).click();await card.locator('.product-info').filter({hasText:'Artwork 2'}).waitFor();for(const label of ['Product image','Product title','CTA','Next available']){const toggle=card.getByRole('checkbox',{name:label,exact:true});if(!await toggle.isChecked())await toggle.check();}
 }
 await editor.getByText('Saved · Draft',{exact:true}).waitFor();sections=await read();
 const originalUrl=page.url();const nodes=await preview().locator('#sc-local-sections').evaluate(root=>{window.clickNode=root;return root.children.length});assert(nodes>0);
 const frameIdentity=await editor.locator('body').evaluate(()=>window.clickIdentity=crypto.randomUUID());
 const click=async(id,selector='')=>{
  const target=preview().locator(`[data-section-id="${id}"]${selector}`);await target.first().evaluate(n=>window.clickedPreviewNode=n);await target.first().click();
  await page.waitForFunction(()=>document.querySelector('.st-key-crm-composer-controls [role="tab"][aria-selected="true"]')?.textContent==='Editor');
  const card=editor.locator(`[data-id="${id}"]`);await card.locator('.title[aria-expanded="true"]').waitFor();
  assert.match(await card.getAttribute('class'),/preview-selected/);assert.equal(await preview().locator('[data-selected]').getAttribute('data-section-id'),id);assert.equal(page.url(),originalUrl);assert(await target.first().evaluate(n=>n===window.clickedPreviewNode),'preview DOM retained');
 };
 for(const device of ['Desktop','Mobile']){
  await page.locator(`[class*="device_${device}"] button:visible`).click();
  for(const start of ['Settings','Templates']){await tab(start).click();await click(html.id,' strong');assert.equal(await editor.locator(`[data-id="${html.id}"] textarea:not([readonly])`).inputValue(),source);}
  await click(html.id,' img');await click(html.id,' a');await click(html.id,' div');await click(duplicate.id,' strong');await click(button.id,' a');await click(image.id,' img');
  {const cat=sections.find(s=>s.type==='catalogue');for(const element of [' img',' p',' [style*="font-size:16px"]',' [style*="text-transform:uppercase"]'])await click(cat.id,element);}
  // Keyboard selects the same stable section, without following email links.
  const node=preview().locator(`[data-section-id="${duplicate.id}"]`);await node.focus();await node.press('Enter');assert.equal(await preview().locator('[data-selected]').getAttribute('data-section-id'),duplicate.id);
  assert.deepEqual(await read(),sections);assert.equal(await editor.locator('body').evaluate(()=>window.clickIdentity),frameIdentity,'section editor must stay mounted');
 }
 await tab('Settings').click();const subject=page.getByRole('textbox',{name:'Subject',exact:true});const updatedSubject=(await subject.inputValue())+' click-edit';await subject.fill(updatedSubject);await click(html.id,' strong');await tab('Settings').click();assert.equal(await subject.inputValue(),updatedSubject);await tab('Editor').click();
 // Preserve a pending source edit when another section is selected.
 await click(html.id,' strong');const area=editor.locator(`[data-id="${html.id}"] textarea:not([readonly])`);await area.fill(source+'<p>Unsaved selection edit</p>');await click(duplicate.id,' strong');await click(html.id,' strong');assert.equal(await area.inputValue(),source+'<p>Unsaved selection edit</p>');
 await editor.locator(`[data-id="${duplicate.id}"]`).getByRole('button',{name:'Delete section',exact:true}).click();await editor.getByRole('button',{name:'Confirm delete section',exact:true}).click();await click(html.id,' a');assert.equal(await preview().locator(`[data-section-id="${duplicate.id}"]`).count(),0);
 await editor.locator(`[data-id="${image.id}"]`).getByRole('button',{name:'Visible section — click to hide',exact:true}).click();await preview().locator(`[data-section-id="${image.id}"]`).waitFor({state:'detached'});await click(button.id,' a');
 await preview().locator('body').click({position:{x:5,y:5}});await preview().getByRole('status').filter({hasText:'Fixed Header'}).waitFor();
 assert.equal(await page.getByTestId('stException').count(),0);assert.deepEqual(errors,[]);
 results.push({kind,desktop:true,mobile:true,stable_ids:true,duplicate:true,reordered:true,tabs:true,keyboard:true,content_unchanged:true,editor_retained:true,preview_dom_retained:true,unsaved_edits_preserved:true,deleted_and_hidden:true,fixed_brand_feedback:true,catalogue:true});
 }catch(e){console.log((await page.locator('body').innerText()).slice(0,5000));throw e;}finally{await page.close();}
}fs.writeFileSync('docs/email-click-edit-validation-20261014.json',JSON.stringify({results},null,2));console.log(JSON.stringify(results));}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
