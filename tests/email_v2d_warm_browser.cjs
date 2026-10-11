const {chromium}=require('playwright'),fs=require('fs'),crypto=require('crypto');
const stats=a=>{a.sort((a,b)=>a-b);return {n:a.length,p50_ms:a[Math.floor(a.length/2)],p95_ms:a[Math.ceil(a.length*.95)-1]}};
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),results=[];
 try{for(const width of [1440,768,390])for(const label of ['before','after']){
  const page=await browser.newPage({viewport:{width,height:900}});
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.goto(`http://127.0.0.1:${label==='before'?8555:8554}/?actor=${crypto.randomUUID()}&delay=0&nav=1`);
  const list=()=>page.frameLocator('iframe[title="support_email_page.support_email_desktop"]').locator('.conversation').first();
  await list().waitFor();const samples=[];
  for(let i=0;i<11;i++){
   await page.getByRole('button',{name:'Leave fixture Email',exact:true}).evaluate(button=>button.click());
   const back=page.getByRole('button',{name:'Return to fixture Email',exact:true});await back.waitFor();
   const elapsed=await back.evaluate(button=>new Promise((resolve,reject)=>{
    const start=performance.now();button.click();
    function frame(){const box=document.querySelector('iframe[title="support_email_page.support_email_desktop"]'),row=box?.contentDocument?.querySelector('.conversation');
     if(box?.getBoundingClientRect().height>0&&row?.getBoundingClientRect().height>0){resolve(performance.now()-start);return;}
     if(performance.now()-start>20000){reject(new Error('Visible list return timed out'));return;}requestAnimationFrame(frame);}
    requestAnimationFrame(frame);
   }));
   if(i)samples.push(elapsed);
  }
  results.push({width,label,warm_return_list:stats(samples)});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync('docs/email-inbox-outlook-v2d-evidence/warm-return.json',JSON.stringify(results,null,2));console.log(results);
})().catch(e=>{console.error(e);process.exitCode=1});
