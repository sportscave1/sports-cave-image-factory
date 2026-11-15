// Real shared Campaign/Automation UI; disposable loopback SQL; no outbound HTTP.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const mode=process.env.EMAIL_V6_MODE||'campaign',port=process.env.EMAIL_V6_UI_PORT||8556;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function sql(query,args=[]){const r=await fetch('http://127.0.0.1:8896',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sql:query,args})});assert.ok(r.ok);return (await r.json()).rows;}
(async()=>{const results=[];let campaignSource;
for(const channel of (process.env.EDITOR_CHANNEL?[process.env.EDITOR_CHANNEL]:['chrome','msedge']))for(const width of (process.env.EDITOR_WIDTH?[Number(process.env.EDITOR_WIDTH)]:[1440,390])){
 const browser=await chromium.launch({channel,headless:true});let page;
 try{
  page=await browser.newPage({viewport:{width,height:1000}});page.setDefaultTimeout(20000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto(`http://127.0.0.1:${port}/?fixture_checkout=1&fixture_discount=1&fixture_run=${Date.now()}`);
  // Hide only the fixture's giant SQL diagnostics, which otherwise overlap the
  // narrow viewport. Real editor controls remain unchanged and pointer-tested.
  await page.addStyleTag({content:'#email-profile{display:none!important}'});
  if(mode==='campaign'){
   await page.locator('.sc-home-row').first().waitFor();
   campaignSource??=(await sql("SELECT document FROM crm_campaign_drafts WHERE created_by='email-performance-fixture' LIMIT 1"))[0].document;
  }
  const row={mode,channel,width,metrics:{}};
  async function timed(name,action,ready){const start=performance.now();await action();await ready();const ms=performance.now()-start;(row.metrics[name]??=[]).push(ms);return ms;}
  async function open(){
   if(mode==='automation')await page.getByRole('button',{name:'Edit Email',exact:true}).first().click();
   else{await page.locator('.st-key-crm-home-table [data-testid=stPopoverButton]').first().click();await page.getByRole('button',{name:'Edit',exact:true}).click();}
   if(mode==='automation')await page.getByRole('tab',{name:'Editor',exact:true}).waitFor();
   else await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();
  }
  await timed('first_editor_shell_tool_wall_ms',open,async()=>{});
  await timed('editor_tab_tool_wall_ms',()=>page.getByRole('tab',{name:'Editor',exact:true}).click(),()=>page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]').locator('textarea').first().waitFor());
  const controls=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]'),preview=page.frameLocator('.st-key-crm-composer-preview iframe');
  const saved=()=>controls.getByText('Saved · Draft',{exact:true}).waitFor();
  const area=()=>controls.locator('textarea').first();
  await area().fill('<p>V6 base creative</p>');await preview.getByText('V6 base creative',{exact:true}).first().waitFor();await saved();
  for(const count of [3,30]){
   while(await controls.locator('.section').count()<count)await controls.getByRole('button',{name:'Duplicate section',exact:true}).first().click();
   await saved();
   row.metrics['hide_show_'+count+'_js_frame_ms']=await controls.locator('body').evaluate(async()=>{const samples=[];for(let i=0;i<12;i++){const start=performance.now();document.querySelector('.visibility').click();await new Promise(requestAnimationFrame);samples.push(performance.now()-start)}return samples;});
   const ids=await controls.locator('.section').evaluateAll(ns=>ns.map(n=>n.dataset.id));
   await controls.getByRole('button',{name:'Drag to reorder section; Alt + Up or Down'}).first().press('Alt+ArrowDown');
   assert.deepEqual((await controls.locator('.section').evaluateAll(ns=>ns.map(n=>n.dataset.id))).slice(0,2),[ids[1],ids[0]]);
   await saved();
   const long='<p style="color:#123456">Long custom creative</p>'.repeat(500);
   for(let i=0;i<3;i++){
    const marker=`Long-${count}-${i}`;
    await timed('html_'+count+'_tool_wall_ms',()=>area().fill(`<h2>${marker}</h2>`+long),()=>preview.getByText(marker,{exact:true}).waitFor());
   }
   await area().fill('<p>V6 base creative</p>');await saved();
  }
  // New V6: unbound and unfinished discount presentation remains editable/saveable.
  await controls.locator('#add summary').click();await controls.getByRole('button',{name:'Add Discount',exact:true}).click();
  const discount=controls.getByRole('textbox',{name:'Discount HTML',exact:true});await discount.waitFor();
  for(const source of ['<p>{{discount_value}}</p>','<p>{{discount_code}}</p>','<table><tr><td>Unfinished creative']){
   await discount.fill(source);await saved();assert.equal(await preview.getByRole('alert').count(),0);
  }
  const custom='<style>.v6-title{color:#123456;padding:17px}</style><!-- authored comment --><h2 class="v6-title">Creative without code</h2>';
  await discount.fill(custom);await preview.getByText('Creative without code',{exact:true}).waitFor();await saved();
  assert.equal(await preview.getByText('Creative without code',{exact:true}).evaluate(n=>getComputedStyle(n).paddingTop),'17px');
  const card=controls.locator('.section').filter({has:discount});
  await card.getByRole('button',{name:'Visible section — click to hide'}).click();assert.equal(await preview.getByText('Creative without code',{exact:true}).count(),0);
  await card.getByRole('button',{name:'Hidden section — click to show'}).click();await preview.getByText('Creative without code',{exact:true}).waitFor();
  await card.getByRole('button',{name:'Duplicate section',exact:true}).click();assert.equal(await controls.getByRole('textbox',{name:'Discount HTML',exact:true}).count(),2);
  await controls.getByRole('textbox',{name:'Discount HTML',exact:true}).last().fill('<p>Delete me</p>');await saved();
  const copied=controls.locator('.section').filter({has:controls.getByRole('textbox',{name:'Discount HTML',exact:true})}).last();
  await copied.getByRole('button',{name:'Delete section',exact:true}).click();await copied.getByRole('button',{name:'Confirm delete section',exact:true}).click();
  await controls.getByRole('button',{name:'Undo delete section'}).click();await saved();
  if(mode==='automation'){
   await controls.getByRole('button',{name:'Connect Shopify discount'}).first().click();
   const pick=controls.getByRole('button',{name:'Select discount FIXTURE5',exact:true});await pick.waitFor();
   while(!(await pick.isEnabled()))await sleep(50);await pick.click();await saved();
   await controls.getByRole('button',{name:'Disconnect checkout discount'}).waitFor();
   await controls.locator('.section').filter({has:controls.getByRole('textbox',{name:'Discount HTML',exact:true})}).first().getByRole('button',{name:'Visible section — click to hide'}).click();await saved();
   assert.equal(await controls.getByRole('button',{name:'Disconnect checkout discount'}).count(),1);
   await controls.getByRole('button',{name:'Disconnect checkout discount'}).click();await saved();
   assert.equal(await controls.getByRole('button',{name:'Disconnect checkout discount'}).count(),0);
  }
  await timed('mobile_switch_tool_wall_ms',()=>page.locator('.st-key-crm-preview-devices button:visible').nth(1).click(),()=>preview.locator('body').waitFor());
  await saved();
  const before=await controls.locator('textarea').evaluateAll(ns=>ns.map(n=>n.value));
  await page.screenshot({path:`tmp/email-v6-${mode}-${channel}-${width}.png`,fullPage:false});
  const back=mode==='automation'?'Flow':'← Campaigns';await page.getByRole('button',{name:back,exact:true}).click();
  await timed('reopen_tool_wall_ms',open,async()=>{});await page.getByRole('tab',{name:'Editor',exact:true}).click();await controls.locator('textarea').first().waitFor();
  assert.deepEqual(await controls.locator('textarea').evaluateAll(ns=>ns.map(n=>n.value)),before,'Exact source survives reopening');
  assert.equal(await page.getByTestId('stException').count(),0);assert.deepEqual(errors,[]);
  const sends=await sql('select count(*)::int as total from crm_marketing_sends');assert.equal(sends[0].total,0);
  row.passed=true;results.push(row);fs.writeFileSync(`tmp/email-v6-${mode}-browser.json`,JSON.stringify(results,null,2));console.log(mode,channel,width,'passed');
  if(mode==='campaign')await sql("UPDATE crm_campaign_drafts SET document=$1::jsonb,version=version+1 WHERE created_by='email-performance-fixture'",[JSON.stringify(campaignSource)]);
 }catch(e){if(page){fs.writeFileSync('tmp/email-v6-failure.txt',await page.locator('body').innerText()+'\nCOMPONENT\n'+await page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]').locator('body').innerText());await page.screenshot({path:'tmp/email-v6-failure.png'});}throw e}finally{await browser.close()}
}
})().catch(e=>{console.error(e);process.exit(1)});
