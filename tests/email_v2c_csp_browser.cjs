const {chromium}=require('playwright'),fs=require('fs'),assert=require('node:assert/strict');
const dir='docs/email-inbox-outlook-v2c-evidence',documents=JSON.parse(fs.readFileSync(`${dir}/attack-documents.json`));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),result=[];
 try{for(const width of [1440,768,390]){
  const page=await browser.newPage({viewport:{width,height:900},ignoreHTTPSErrors:true});
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  for(const attack of documents){
   await fetch('http://127.0.0.1:8843/__reset',{method:'POST'});
   await page.setContent('<iframe sandbox="allow-same-origin" referrerpolicy="no-referrer"></iframe>');
   await page.locator('iframe').evaluate((f,doc)=>{f.srcdoc=doc},attack.document);
   await page.waitForTimeout(200);
   const hits=await(await fetch('http://127.0.0.1:8843/__hits')).json();assert.equal(hits.length,0,attack.name);
   assert.equal(await page.locator('iframe').evaluate(f=>Boolean(f.contentWindow.executed)),false);
   result.push({width,attack:attack.name,requests:hits.length});
  }await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(`${dir}/csp-browser.json`,JSON.stringify(result,null,2));console.log(`${result.length} malicious-document/CSP cases passed with zero requests`);
})().catch(e=>{console.error(e);process.exitCode=1});
