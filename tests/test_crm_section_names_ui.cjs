// Real shared editor in Campaigns and Automations; external requests blocked.
const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 for(const mode of ['campaign','automation']){
  const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();await page.setViewportSize({width:1440,height:1000});
  await page.goto(mode==='campaign'?'http://127.0.0.1:8541/':'http://127.0.0.1:8540/?fixture_checkout=1&fixture_run=rename'+Date.now());
  async function editor(){if(mode==='automation')await page.getByRole('button',{name:'Edit Email',exact:true}).first().click();await page.getByRole('tab',{name:'Editor',exact:true}).click();}
  await editor();
  const frame=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]'),card=frame.locator('.section').first();
  await card.locator('.title').waitFor();const defaultLabel=await card.locator('.title').innerText();
  const wasOpen=await card.locator('.title').getAttribute('aria-expanded');
  assert.equal(await card.locator('.section-name-control').evaluate(e=>e.previousElementSibling.className),'visibility');
  async function rename(){await card.getByRole('button',{name:'Section options',exact:true}).click();await card.getByRole('menuitem',{name:'Rename',exact:true}).click();}
  await rename();const input=card.getByRole('textbox',{name:'Section name',exact:true});
  assert.equal(await input.inputValue(),defaultLabel);await input.fill('Canceled');await input.press('Escape');
  assert.equal(await card.locator('.title').innerText(),defaultLabel);assert.equal(await card.locator('.title').getAttribute('aria-expanded'),wasOpen);
  await rename();await input.fill('Hero / Heading');await input.press('Enter');
  await card.getByRole('button',{name:'Edit Hero / Heading',exact:true}).waitFor();
  assert.equal(await card.locator('.title').getAttribute('aria-expanded'),wasOpen);
  assert.equal(await card.locator('.visibility').getAttribute('aria-pressed'),'true');
  if(mode==='campaign'){await card.getByRole('textbox',{name:'Hero / Heading HTML',exact:true}).fill('<p>Unchanged customer content</p>');await card.getByRole('textbox',{name:'Hero / Heading HTML',exact:true}).press('Tab');}
  const save=page.getByRole('button',{name:'Save draft',exact:true});
  // Automation section edits persist through the existing autosave. A disabled
  // Save means the server already saved it; the reload below verifies that.
  if(await save.isEnabled())await save.click();
  await page.getByRole('tab',{name:'Settings',exact:true}).click();await page.getByRole('tab',{name:'Editor',exact:true}).click();
  await card.getByRole('button',{name:'Edit Hero / Heading',exact:true}).waitFor();
  await page.reload();await editor();await card.getByRole('button',{name:'Edit Hero / Heading',exact:true}).waitFor();
  await rename();await input.fill('Discarded');await card.getByRole('button',{name:'Cancel rename',exact:true}).click();
  assert.equal(await card.locator('.title').innerText(),'Hero / Heading');
  await rename();await card.getByRole('button',{name:'Reset section name to default',exact:true}).click();
  await card.getByRole('button',{name:'Edit HTML Section 1',exact:true}).waitFor();
  await rename();await input.fill('Customer Artwork');await card.getByRole('button',{name:'Save section name',exact:true}).click();
  await card.getByRole('button',{name:'Edit Customer Artwork',exact:true}).waitFor();
  await card.getByRole('button',{name:'Duplicate section',exact:true}).click();
  await frame.getByRole('button',{name:'Edit Customer Artwork',exact:true}).nth(1).waitFor();
  await card.getByRole('button',{name:'Drag to reorder section; Alt + Up or Down',exact:true}).press('Alt+ArrowDown');
  await frame.getByRole('button',{name:'Edit Customer Artwork',exact:true}).first().waitFor();
  await page.screenshot({path:'tmp/section-rename-'+mode+'.png',fullPage:true});
  assert.equal(await page.getByTestId('stException').count(),0);await context.close();
 }
 console.log('PASS: Campaigns and Automations rename/save/cancel/Enter/Escape/reset, tab switching, refresh/reopen, duplicate/reorder; menu leaves visibility and expansion unchanged');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
