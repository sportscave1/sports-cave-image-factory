// Remaining workflow timings. Opens local review/pickers; never confirms a send.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const mode=process.env.EMAIL_V6_MODE||'campaign',port=process.env.EMAIL_V6_UI_PORT||8556,label=process.env.EMAIL_V6_LABEL||'after';
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});const rows=[];
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(20000);
 await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 for(let i=0;i<6;i++){
  const record={};const timed=async(name,fn)=>{const start=performance.now();await fn();record[name]=performance.now()-start;};
  await timed('page_to_list_tool_wall_ms',async()=>{await page.goto(`http://127.0.0.1:${port}/?fixture_checkout=1&fixture_discount=1&fixture_run=audit${Date.now()}`);await page.addStyleTag({content:'#email-profile{display:none!important}'});await (mode==='automation'?page.getByRole('button',{name:'Edit Email',exact:true}).first():page.locator('.sc-home-row').first()).waitFor()});
  const open=async(index=0)=>{if(mode==='automation')await page.getByRole('button',{name:'Edit Email',exact:true}).nth(index).click();else{await page.locator('.st-key-crm-home-table [data-testid=stPopoverButton]').nth(index).click();await page.getByRole('button',{name:'Edit',exact:true}).click()}await page.getByRole('tab',{name:'Editor',exact:true}).waitFor()};
  await timed('list_to_editor_shell_tool_wall_ms',()=>open());
  if(mode==='campaign'){
   await timed('review_shell_tool_wall_ms',async()=>{await page.getByRole('button',{name:'Send now',exact:true}).click();await page.locator('.st-key-crm-send-review-summary').waitFor()});
   await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'hidden'});
  }else{
   await page.getByRole('tab',{name:'Editor',exact:true}).click();
   const frame=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]');await frame.locator('textarea').first().waitFor();
   const openPicker=async()=>{await frame.locator('#add summary').click();await frame.getByRole('button',{name:'Add Discount',exact:true}).click();if(label==='after'){await frame.getByRole('textbox',{name:'Discount HTML',exact:true}).waitFor();await frame.getByText('Saved · Draft',{exact:true}).waitFor();await frame.getByRole('button',{name:'Connect Shopify discount'}).first().click()}await frame.getByRole('searchbox',{name:'Search Shopify discounts'}).waitFor()};
   await timed('discount_picker_shell_tool_wall_ms',openPicker);
   await frame.locator('body').evaluate(()=>{window.auditArgs=null;addEventListener('message',e=>{if(e.data.type==='streamlit:render')window.auditArgs=e.data.args})});
   await timed('discount_search_ready_tool_wall_ms',async()=>{const field=frame.getByRole('searchbox',{name:'Search Shopify discounts'});await field.fill('FIXTURE5');await field.press('Enter');const end=Date.now()+15000;while(!(await frame.locator('body').evaluate(()=>window.auditArgs?.discount?.term==='FIXTURE5'&&!window.auditArgs.discount.pending&&window.auditArgs.discount.loaded))){if(Date.now()>end)throw Error('Discount search did not settle');await new Promise(r=>setTimeout(r,20))}});
   await timed('discount_apply_and_save_tool_wall_ms',async()=>{await frame.getByRole('button',{name:'Select discount FIXTURE5',exact:true}).click();await frame.getByRole('button',{name:'Change Shopify discount'}).first().waitFor();await frame.getByText('Saved · Draft',{exact:true}).waitFor()});
  }
  await timed('return_to_list_tool_wall_ms',async()=>{await page.getByRole('button',{name:mode==='automation'?'Flow':'← Campaigns',exact:true}).click();await (mode==='automation'?page.getByRole('button',{name:'Edit Email',exact:true}).first():page.locator('.sc-home-row').first()).waitFor()});
  await timed('different_email_open_tool_wall_ms',()=>open(1));
  assert.equal(await page.getByTestId('stException').count(),0);rows.push(record);
 }
 const response=await fetch('http://127.0.0.1:8896',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sql:'SELECT count(*)::int AS total FROM crm_marketing_sends'})});assert.equal((await response.json()).rows[0].total,0);
 fs.writeFileSync(`tmp/email-v6-${label}-${mode}-controls.json`,JSON.stringify(rows,null,2));console.log(label,mode,'six controlled workflow samples; zero sends');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
