// Fresh isolated Python process and empty ReadService each sample. No production app.
const {chromium}=require('playwright'),{spawn}=require('child_process'),fs=require('fs'),crypto=require('crypto');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),results=[];
 try{for(const width of [1440,390])for(const label of ['before','after']){
  const samples=[];
  for(let i=0;i<3;i++){
   const log=fs.openSync(`docs/email-inbox-outlook-v2c-evidence/cold-${label}-${width}-${i}.log`,'w');
   const start=performance.now();
   const child=spawn('.venv/Scripts/python.exe',['-m','uvicorn','tests.email_v2c_server:app','--host','127.0.0.1','--port','8556'],
     {windowsHide:true,env:{...process.env,PYTHONUTF8:'1',EMAIL_V2C_BASELINE:label==='before'?'1':'0',STREAMLIT_BROWSER_GATHER_USAGE_STATS:'false'},stdio:['ignore',log,log]});
   let page;
   try{
    while(true){try{const response=await fetch('http://127.0.0.1:8556/_stcore/health');if(response.ok)break;}catch{}
     if(performance.now()-start>20000)throw Error('Local cold fixture did not start');
     await new Promise(r=>setTimeout(r,25));
    }
    const ready=performance.now()-start;
    page=await browser.newPage({viewport:{width,height:900}});
    await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
    await page.goto(`http://127.0.0.1:8556/?actor=${crypto.randomUUID()}`);
    await page.frameLocator('iframe[title="support_email_page.support_email_desktop"]').locator('.conversation').first().waitFor();
    samples.push({process_to_health_ms:ready,process_to_list_ms:performance.now()-start});
   }finally{
    if(page)await page.close();
    await new Promise(resolve=>{child.once('exit',resolve);child.kill();});fs.closeSync(log);
   }
  }
  results.push({width,label,n:3,samples});
 }
 }finally{await browser.close();}
 fs.writeFileSync('docs/email-inbox-outlook-v2c-evidence/cold-start.json',JSON.stringify(results,null,2));console.log(results);
})().catch(e=>{console.error(e);process.exitCode=1});
