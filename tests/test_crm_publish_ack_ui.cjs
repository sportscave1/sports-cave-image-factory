// Paint-visible acknowledgement comparison, with no backend/network request.
const {chromium}=require('playwright'),{execFileSync}=require('node:child_process'),fs=require('fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const result={};
 for(const phase of ['before','after']){
  const source=phase==='before'?execFileSync('git',['show','736cd66:components/crm_sections/automation_publish.js'],{encoding:'utf8'}):fs.readFileSync('components/crm_sections/automation_publish.js','utf8');
  const samples=[];let visible=0;
  for(let i=0;i<30;i++){
   const page=await browser.newPage();await page.setContent('<div class="st-key-automation-toolbar"><div><button>Publish changes</button></div></div>');
   await page.evaluate(()=>{window.scCampaignFlushSections=()=>Promise.resolve();document.querySelector('button').onclick=()=>window.accepted=true;});
   await page.addScriptTag({content:source});
   const observed=await page.evaluate(()=>new Promise(resolve=>{
    const at=performance.now();document.querySelector('button').click();
    requestAnimationFrame(()=>resolve({ms:performance.now()-at,text:document.querySelector('[role=status]')?.textContent||'',accepted:!!window.accepted}));
   }));
   assert.equal(observed.accepted,true);
   if(observed.text)visible++;
   if(phase==='after')assert.equal(observed.text,'Submitting publication…');
   samples.push(observed.ms);await page.close();
  }
  samples.sort((a,b)=>a-b);result[phase]={n:30,visibleAtNextPaint:visible,p50_ms:samples[15],p95_ms:samples[28]};
 }
 assert.equal(result.before.visibleAtNextPaint,0);assert.equal(result.after.visibleAtNextPaint,30);
 fs.writeFileSync('tmp/email_v4_ack.json',JSON.stringify(result,null,2));console.log('PASS immediate acknowledgement',JSON.stringify(result));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
