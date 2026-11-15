const{chromium}=require('playwright');
(async()=>{
 const b=await chromium.launch({channel:'chrome',headless:true});
 try{
  const p=await b.newPage({viewport:{width:1440,height:950}});
  await p.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await p.goto('http://127.0.0.1:'+(process.env.EDITOR_PORT||8545)+'/?fixture_checkout=1');
  await p.getByRole('button',{name:'Edit Email',exact:true}).first().click();
  await p.getByRole('tab',{name:'Editor',exact:true}).click();
  const f=p.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]');
  await f.locator('.visibility').first().waitFor();
  const samples=[];
  for(let i=0;i<5;i++){
   await p.waitForTimeout(500);
   samples.push(await f.locator('body').evaluate(async()=>{
    const start=performance.now();document.querySelector('.visibility').click();
    while(performance.now()-start<10000){
     const v=parent.document.querySelector('.st-key-crm-composer-preview iframe');
     if(v?.contentDocument?.body&&!v.contentDocument.body.textContent.includes('Still thinking it over?'))return performance.now()-start;
     await new Promise(r=>setTimeout(r,10));
    }throw Error('Preview did not change within 10 seconds');
   }));
   await f.getByRole('button',{name:'Hidden section — click to show'}).click();
   await p.waitForTimeout(900);
  }
  console.log(samples);require('fs').writeFileSync('tmp/local-editor-benchmark-'+(process.env.EDITOR_PORT||8545)+'.json',JSON.stringify(samples));
 }finally{await b.close();}
})().catch(e=>{console.error(e);process.exit(1)});
