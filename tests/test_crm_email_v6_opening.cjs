// Real editor, disposable SQL, blocked external requests. Timings start at DOM click.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('node:assert/strict');
async function revisionDigest(){
 const response=await fetch('http://127.0.0.1:8896',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sql:"SELECT md5(string_agg(id::text||version::text||document::text, '' ORDER BY id)) AS digest FROM crm_campaign_drafts",args:[]})});
 assert.ok(response.ok);return (await response.json()).rows[0].digest;
}
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const samples=[],profiles=[],label=process.env.EMAIL_V5_LABEL||'after';
 for(let session=0;session<12;session++){
  const context=await browser.newContext({viewport:{width:session===11?390:1440,height:1000}});
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();page.setDefaultTimeout(20000);
  await page.goto('http://127.0.0.1:8556/');await page.locator('.sc-home-row').first().waitFor();
  const original=await revisionDigest();
  async function counters(){const prior=await page.locator('#email-profile').innerText();await page.getByRole('button',{name:'Profile snapshot',exact:true}).evaluate(e=>e.click());await page.waitForFunction(x=>document.querySelector('#email-profile')?.textContent!==x,prior);return JSON.parse(await page.locator('#email-profile').innerText());}
  async function click(button){await button.evaluate(e=>{window.v5start=performance.now();e.click()});}
  async function elapsed(){return page.evaluate(()=>performance.now()-window.v5start);}
  for(const kind of ['cold','warm']){
   const before=await counters();await page.locator('.st-key-crm-home-table [data-testid=stPopoverButton]').first().click();
   await click(page.getByRole('button',{name:'Edit',exact:true}));await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();
   const row={session,kind,firstUsefulMs:await elapsed()};await page.locator('.st-key-crm-composer-preview iframe').waitFor();row.previewReadyMs=await elapsed();
   const after=await counters();row.reads=after.queries-before.queries;
   const sql=(after.sql||[]).slice((before.sql||[]).length);row.dbWaitMs=sql.reduce((n,s)=>n+s.ms,0);profiles.push({session,kind,sql,server:after.server_profile});
   fs.writeFileSync('tmp/email-v5-'+label+'.json',JSON.stringify({samples,profiles},null,2));
   await click(page.getByRole('tab',{name:'Editor',exact:true}));await page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]').getByRole('textbox').first().waitFor();row.editorTabMs=await elapsed();
   await page.evaluate(()=>window.v5preview=document.querySelector('.st-key-crm-composer-preview iframe'));
   await click(page.locator('.st-key-crm-preview-devices button:visible').nth(1));await page.waitForFunction(()=>[...document.querySelectorAll('.st-key-crm-preview-devices button')].filter(b=>b.getClientRects().length)[1]?.getAttribute('kind')==='primary');row.previewSwitchMs=await elapsed();
   await click(page.getByRole('tab',{name:'Templates',exact:true}));await page.getByText('Email defaults',{exact:true}).waitFor();row.templatesMs=await elapsed();
   await click(page.getByRole('tab',{name:'Settings',exact:true}));await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();
   await click(page.getByRole('button',{name:'Send test',exact:true}));await page.getByRole('textbox',{name:'Send test email',exact:true}).waitFor();row.sendTestSetupMs=await elapsed();
   await page.keyboard.press('Escape');await page.getByRole('textbox',{name:'Send test email',exact:true}).waitFor({state:'hidden'});
   assert.equal(await page.evaluate(()=>window.v5preview===document.querySelector('.st-key-crm-composer-preview iframe')),true);
   await click(page.getByRole('button',{name:'← Campaigns',exact:true}));await page.locator('.sc-home-row').first().waitFor();row.backMs=await elapsed();
   assert.equal(await page.getByTestId('stException').count(),0);samples.push(row);
   assert.equal(await revisionDigest(),original,'Opening, preview, tabs and closing preserve every stored draft and revision');
  }
  await context.close();
 }
 fs.writeFileSync('tmp/email-v5-'+label+'.json',JSON.stringify({samples,profiles},null,2));console.log(JSON.stringify({label,samples}));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
