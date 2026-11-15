// Real Streamlit composer + isolated SQL. No production or provider requests.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('fs');
const sql=async(sql,args=[])=>{const r=await fetch('http://127.0.0.1:8873',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sql,args})});assert.ok(r.ok);return (await r.json()).rows;};
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const context=await browser.newContext({viewport:{width:1440,height:950}});
 await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage();page.setDefaultTimeout(20000);const times={open:[],tabs:[],preview:[],close:[]};
 const checkout=process.env.EMAIL_V4_CHECKOUT==='1',baseline=process.env.EMAIL_PROFILE_AUTOMATION_BASELINE==='1';
 const first=Date.now();
 await page.goto('http://127.0.0.1:8533/?'+(checkout?'fixture_checkout=1&fixture_checkout_live=1':'fixture_toolbar_live=1')+'&fixture_run=v4'+Date.now());
 await page.getByRole('button',{name:'Edit Email',exact:true}).first().waitFor();
 const initialFlowMs=Date.now()-first;
 const [flow]=await sql('SELECT id,config FROM crm_automations WHERE name=$1 ORDER BY updated_at DESC LIMIT 1',[checkout?'Abandoned checkout · local fixture':'Welcome series · local fixture']);
 const read=async()=> (await sql('SELECT config FROM crm_automations WHERE id=$1',[flow.id]))[0].config;
 const original=await read();
 for(let pass=0;pass<8;pass++){
  let at=Date.now();await page.getByRole('button',{name:'Edit Email',exact:true}).first().click();await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();times.open.push(Date.now()-at);
  const subject=await page.getByRole('textbox',{name:'Subject',exact:true}).inputValue();
  for(const tab of ['Editor','Templates','Settings']){
   at=Date.now();await page.getByRole('tab',{name:tab,exact:true}).click();
   if(tab==='Editor')await page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]').getByRole('textbox').first().waitFor();
   else if(tab==='Templates')await page.getByText('Email defaults',{exact:true}).waitFor();
   else await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();
   times.tabs.push(Date.now()-at);
  }
  for(const index of [1,0]){at=Date.now();await page.locator('.st-key-crm-preview-devices button:visible').nth(index).click();times.preview.push(Date.now()-at);}
  assert.equal(await page.getByRole('textbox',{name:'Subject',exact:true}).inputValue(),subject);
  assert.equal(await page.getByRole('button',{name:'Save draft',exact:true}).isDisabled(),true);
  assert.equal(await page.getByText(/Unpublished changes/).count(),0);
  at=Date.now();await page.getByRole('button',{name:'Flow',exact:true}).click();await page.getByRole('button',{name:'Edit Email',exact:true}).first().waitFor();times.close.push(Date.now()-at);
  if(!baseline)assert.deepEqual(await read(),original,'Open/tab/preview/close must not write draft, revision or publication');
 }
 assert.equal(await page.getByTestId('stException').count(),0);
 const result={...times,initialFlowMs,revisionBefore:original.revision,revisionAfter:(await read()).revision};
 fs.writeFileSync('tmp/email_v4_ui_timings'+(checkout?'_checkout':'')+(baseline?'_before':'')+'.json',JSON.stringify(result,null,2));
 console.log(baseline?'Baseline no-touch editor measurements':'PASS no-touch editor: eight cycles retain exact SQL config and revision',JSON.stringify(result));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
