// Existing durable executor runs in a localhost fixture thread. SQL adapter is serialized.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('fs');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const context=await browser.newContext({viewport:{width:1440,height:950}});
 await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage();page.setDefaultTimeout(20000);const result={};
 for(const count of [1,3,6]){
  const samples=[];
  for(let i=0;i<4;i++){
   await page.goto(`http://127.0.0.1:8533/?fixture_checkout=1&fixture_steps=${count}&fixture_run=latency${Date.now()}`);
   await page.getByRole('button',{name:'Edit Email',exact:true}).first().click();
   // The Flow page also has Publish now: wait for the requested editor route,
   // not the old toolbar being removed during navigation.
   await page.getByRole('textbox',{name:'Subject',exact:true}).waitFor();
   const toolbar=page.locator('.st-key-automation-toolbar');await toolbar.getByRole('button',{name:'Publish now',exact:true}).waitFor();
   const start=Date.now();await toolbar.getByRole('button',{name:'Publish now',exact:true}).click();
   await toolbar.getByText('Published · Up to date',{exact:true}).waitFor().catch(async error=>{
    console.log('Publication timeout UI:',(await page.locator('body').innerText()).slice(-2500));
    const r=await fetch('http://127.0.0.1:8873',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sql:'SELECT state,attempts,error FROM crm_automation_publish_jobs'})});
    console.log('Local job state:',await r.json());throw error;
   });samples.push(Date.now()-start);
   assert.equal(await page.locator('.st-key-flow-workspace').count(),0);
   assert.equal(await page.getByTestId('stException').count(),0);
  }
  result[count]=samples;
 }
 fs.writeFileSync('tmp/email_v4_full_publication.json',JSON.stringify(result,null,2));console.log('PASS click to verified publication, including actual polling',JSON.stringify(result));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
