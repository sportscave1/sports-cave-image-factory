// Repeated fresh browser sessions; real UI, synthetic Shopify/SQL only.
const {chromium}=require('playwright'),fs=require('node:fs');
const summary=xs=>{xs.sort((a,b)=>a-b);return {median:xs[Math.floor(xs.length/2)],p95:xs[Math.ceil(xs.length*.95)-1],samples:xs.length}};
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true}),result={};
 try{for(const [version,port]of [['before',18732],['after',18731]]){
  result[version]={};for(const flow of ['abandoned','welcome','post_purchase','win_back','fulfilled']){
   const samples={toolbar:[],first_iframe:[],personalized:[]};
   for(let i=0;i<5;i++){
    const page=await browser.newPage({viewport:{width:1100,height:950}});
    await page.route('**/*',r=>{const u=new URL(r.request().url());if(u.hostname==='127.0.0.1')return r.continue();if(u.hostname==='cdn.shopify.com')return r.fulfill({contentType:'image/png',body:fs.readFileSync('tests/fixtures/checkout_product_generated.png')});return r.abort()});
    const text=flow==='welcome'?'Fixture Welcome subscriber content':flow==='abandoned'?'A collector edition <safe> 0':'Fixture Ada Motorsport artwork';
    const t=performance.now();await page.goto('http://127.0.0.1:'+port+'/?flow='+flow);
    await page.locator('[class*="st-key-crm-preview-toolbar-"]').waitFor();samples.toolbar.push(performance.now()-t);
    await page.locator('.st-key-crm-composer-preview iframe').waitFor();samples.first_iframe.push(performance.now()-t);
    await page.frameLocator('.st-key-crm-composer-preview iframe').getByText(text,{exact:true}).first().waitFor({timeout:20000});samples.personalized.push(performance.now()-t);
    await page.close();
   }
   result[version][flow]=Object.fromEntries(Object.entries(samples).map(([k,v])=>[k,summary(v)]));console.log(version,flow,JSON.stringify(result[version][flow]));
  }
 }}finally{await browser.close()}
 fs.writeFileSync('.tmp-preview-ultimate/cold-browser.json',JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
