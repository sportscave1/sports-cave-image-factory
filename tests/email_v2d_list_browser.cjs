const {chromium}=require('playwright'),fs=require('fs'),crypto=require('crypto');
const stats=a=>{a.sort((a,b)=>a-b);return {n:a.length,p50_ms:+a[Math.floor(a.length/2)].toFixed(2),p95_ms:+a[Math.ceil(a.length*.95)-1].toFixed(2)}};
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),rows=[];
 try{for(const width of [1440,768,390]){
  const context=await browser.newContext({viewport:{width,height:900}}),pages={},samples={before:[],after:[]};
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  for(const label of ['before','after'])pages[label]=await context.newPage();
  for(let i=0;i<21;i++)for(const label of i%2?['after','before']:['before','after']){
   const page=pages[label];await page.bringToFront();const t=performance.now();await page.goto(`http://127.0.0.1:${label==='before'?8555:8554}/?actor=${crypto.randomUUID()}`);
   await page.frameLocator('iframe[title="support_email_page.support_email_desktop"]').locator('.conversation').first().waitFor();
   if(i)samples[label].push(performance.now()-t);
  }
  rows.push({width,before:stats(samples.before),after:stats(samples.after)});await context.close();
 } }finally{await browser.close();}
 fs.writeFileSync('docs/email-inbox-outlook-v2d-evidence/list-paint-interleaved.json',JSON.stringify({method:'20 fresh-page list paints per width/version after one warmup; alternating version order each round; same browser/fixture.',results:rows},null,2));console.log(rows);
})().catch(e=>{console.error(e);process.exitCode=1});
