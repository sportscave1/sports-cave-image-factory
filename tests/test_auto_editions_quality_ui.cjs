// Fully intercepted synthetic browser. No live account, app, allocations or assets.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});let checks=0;
try{for(const width of [1280,390]){
 const page=await browser.newPage({viewport:{width,height:800}});let stage='Production Ready',calls=0,rechecks=0;
 await page.route('**/*',route=>{
  const u=new URL(route.request().url());
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/auto_editions/status.html','utf8')});
  if(u.pathname==='/api/auto-editions/status/recheck'){rechecks++;assert.deepEqual(Object.keys(route.request().postDataJSON()),['product_gid']);stage='Preparing';return route.fulfill({json:{ok:true}});}
  if(u.pathname==='/api/auto-editions/status'){calls++;return route.fulfill({json:{rows:[{status:stage,icon:'✅',checkpoint:'Production validation',reason:stage==='Production Ready'?'Validated for approved supplier variants':'Supplier evidence incomplete',actions:stage==='Needs Review'?['recheck']:[]}]}});}
  return route.abort();
 });
 await page.goto('https://quality.local.test/?product_gid=gid%3A%2F%2Fshopify%2FProduct%2F987');
 await page.locator('#stage').getByText('Production Ready',{exact:false}).waitFor();
 assert.equal(await page.locator('#actions button').count(),0);
 assert.equal(await page.locator('#review').isVisible(),false);
 assert(!(await page.locator('body').innerText()).includes('TEST'));
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 stage='Needs Review';await page.getByRole('button',{name:'Refresh',exact:true}).click();
 await page.locator('#stage').getByText('Needs Review',{exact:false}).waitFor();
 assert.equal(calls,2);assert.equal(await page.locator('#reason').innerText(),'Supplier evidence incomplete');
 await page.getByRole('button',{name:'Recheck validation'}).click();await page.locator('#stage').getByText('Preparing',{exact:false}).waitFor();assert.equal(rechecks,1);
 checks++;await page.close();
}console.log(`V16 quality status: ${checks} desktop/mobile scenarios passed; production scope, no manual auto-approval action, no TEST label.`);
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
