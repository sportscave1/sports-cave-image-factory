// Actual shared Streamlit editor with loopback-only, disposable SQL fixtures.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{for(const kind of (process.env.MODULAR_KIND?[process.env.MODULAR_KIND]:['automation','campaign'])){
  const page=await browser.newPage({viewport:{width:Number(process.env.MODULAR_WIDTH||1440),height:1000}});page.setDefaultTimeout(20000);let dialogs=0;const errors=[];
  page.on('dialog',d=>{dialogs++;d.dismiss()});page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  if(kind==='campaign'){
   await page.goto('http://127.0.0.1:18894');await page.getByRole('link',{name:'Open Catalogue fixture',exact:true}).click();
  }else{
   await page.goto('http://127.0.0.1:18895/?fixture_checkout=1&fixture_run=modular-'+Date.now());
   await page.getByRole('button',{name:/Edit Email/i}).first().click();
  }
  const tab=n=>page.getByRole('tab',{name:n,exact:true});await tab('Settings').click();
  const subject=await page.getByRole('textbox',{name:'Subject',exact:true}).inputValue();
  const checkSubject=async()=>{for(let i=0;i<200;i++){if(await page.getByRole('textbox',{name:'Subject',exact:true}).inputValue()===subject)return;await page.waitForTimeout(50);}assert.equal(await page.getByRole('textbox',{name:'Subject',exact:true}).inputValue(),subject);};await tab('Editor').click();
  const f=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]');
  const read=async()=>{
   await f.locator('.section').first().waitFor();
   for(let n=0;n<100;n++){
    const value=await f.locator('body').evaluate(()=>structuredClone([...parent.scEmailDrafts.values()].find(s=>s.sections?.some(p=>p.id===document.querySelector('.section')?.dataset.id))?.sections));
    if(value)return value;await page.waitForTimeout(30);
   }throw Error('Preview state did not synchronize');
  };
  const add=async(kind,position)=>{await f.locator('#add > summary').click();if(position!==undefined)await f.getByRole('combobox',{name:'Insert position',exact:true}).selectOption(String(position));await f.locator(`[data-add="${kind}"]`).click();};
  await f.locator('.section').first().waitFor();
  if(!(await read()).some(s=>s.type==='catalogue'))await add('catalogue');
  const before=await read();await f.locator('#add > summary').click();
  const preset=kind==='automation'?f.getByRole('button',{name:'Insert See It On Your Wall — Interactive Preview',exact:true}):f.locator('[data-add="template"]').first();
  await preset.click();let sections=await read();assert(sections.length>before.length);assert.deepEqual(sections.slice(0,before.length),before);assert.equal(dialogs,0);
  if(kind==='automation')await page.frameLocator('.st-key-crm-composer-preview iframe').getByRole('heading',{name:'See It On Your Wall',exact:true}).waitFor();
  const inserted=sections[before.length];assert.equal(await f.locator(`[data-id="${inserted.id}"] .title`).getAttribute('aria-expanded'),'true');
  await add('html',1);let one=(await read())[1];
  await f.locator(`[data-id="${one.id}"] textarea`).fill('<p style="color:#123456">FIRST independent source</p>');
  await add('html');let two=(await read()).at(-1);
  await f.locator(`[data-id="${two.id}"] textarea`).fill('<p>SECOND independent source</p>');
  await f.locator(`[data-id="${two.id}"] textarea`).press('Tab');
  assert.equal((await read()).find(s=>s.id===one.id).html,'<p style="color:#123456">FIRST independent source</p>');
  const original=(await read()).find(s=>s.id===one.id);
  await f.locator(`[data-id="${one.id}"]`).getByRole('button',{name:'Duplicate section',exact:true}).click();
  sections=await read();let copied=sections[sections.findIndex(s=>s.id===one.id)+1];assert.notEqual(copied.id,one.id);assert.equal(copied.html,original.html);
  await f.locator(`[data-id="${copied.id}"] .title`).click();
  await f.locator(`[data-id="${copied.id}"] textarea`).fill('<p>COPY independent source</p>');
  const drag=f.locator(`[data-id="${copied.id}"] [data-drag]`).first();await drag.focus();await page.keyboard.press('Alt+ArrowUp');
  sections=await read();assert.equal(sections[sections.findIndex(s=>s.id===one.id)-1].id,copied.id);
  await f.locator(`[data-id="${copied.id}"]`).getByRole('button',{name:'Visible section — click to hide'}).click();
  assert.equal((await read()).find(s=>s.id===copied.id).visible,false);
  await f.locator(`[data-id="${copied.id}"]`).getByRole('button',{name:'Delete section',exact:true}).click();await f.getByRole('button',{name:'Confirm delete section'}).click();
  assert(!(await read()).some(s=>s.id===copied.id));
  await f.getByRole('button',{name:'Undo delete section'}).click();assert((await read()).some(s=>s.id===copied.id));
  await f.locator(`[data-id="${copied.id}"]`).getByRole('button',{name:'Delete section',exact:true}).click();await f.getByRole('button',{name:'Confirm delete section'}).click();
  const catalogue=(await read()).find(s=>s.type==='catalogue');const catalogueCard=f.locator(`[data-id="${catalogue.id}"]`);
  if(await catalogueCard.locator('.title').getAttribute('aria-expanded')!=='true')await catalogueCard.locator('.title').click();
  await catalogueCard.getByRole('textbox',{name:'Catalogue CTA',exact:true}).fill('Newest CTA before tab');
  await tab('Settings').click();await checkSubject();await tab('Editor').click();
  assert.equal((await read()).find(s=>s.id===catalogue.id).settings.cta,'Newest CTA before tab');
  const saved=await read();await page.waitForFunction(()=>[...document.querySelectorAll('.st-key-crm-composer-preview iframe')].some(f=>f.contentDocument?.body?.textContent.includes('FIRST independent source')&&f.contentDocument?.body?.textContent.includes('SECOND independent source')));await tab('Settings').click();await checkSubject();
  await tab('Templates').click();await tab('Editor').click();assert.deepEqual(await read(),saved);
  await f.getByText('Saved · Draft',{exact:true}).waitFor();
  await page.reload();await Promise.race([tab('Editor').waitFor(),page.getByRole('button',{name:/Edit Email/i}).first().waitFor()]);if(!await tab('Editor').count())await page.getByRole('button',{name:/Edit Email/i}).first().click();await tab('Editor').click();await f.locator('.section').first().waitFor();assert.deepEqual(await read(),saved);
  // Replacement has its own warning and cancel path, reachable only in Templates.
  await tab('Templates').click();
  if(kind==='automation')await page.getByRole('button',{name:/Lifestyle & Product/}).click();
  await page.getByRole('button',{name:'Apply full template',exact:true}).first().click();
  await page.getByText(/Existing body sections will be overwritten/).waitFor().catch(async e=>{console.log(await page.locator('body').innerText());throw e;});await page.getByRole('button',{name:'Cancel',exact:true}).last().click();
  await tab('Editor').click();assert.deepEqual(await read(),saved);
  await tab('Templates').click();await page.getByRole('button',{name:'Apply full template',exact:true}).first().click();await page.getByRole('button',{name:'Replace email body',exact:true}).click();
  await page.getByText('Template applied to draft',{exact:true}).waitFor().catch(async e=>{console.log(await page.locator('body').innerText());throw e;});
  await tab('Editor').click();await f.locator('.section').first().waitFor();assert.notDeepEqual(await read(),saved);assert((await read()).length>0);assert((await read()).every(s=>!saved.some(old=>old.id===s.id)));
  await tab('Settings').click();await checkSubject();
  assert.equal(await page.getByTestId('stException').count(),0,(await page.getByTestId('stException').allTextContents()).join('\n'));assert.deepEqual(errors,[]);assert.equal(dialogs,0);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
  console.log('PASS '+kind+' width='+(process.env.MODULAR_WIDTH||1440)+': insert preset, position, independent HTML, duplicate, reorder, hide, delete/undo, tabs, SQL save/reopen, replacement cancel/confirm, settings preserved');await page.close();
 }}finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
