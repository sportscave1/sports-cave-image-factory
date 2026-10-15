const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
for(const width of [1280,390]){
 const context=await browser.newContext({viewport:{width,height:800}});let approvals=0,retries=0;
 const rows=[{product_gid:'p',product_title:'Different plaque layout',status:'Blocked',reason:'Visual review required',preparation_hash:'a'.repeat(64)}];
 await context.route('**/*',route=>{const u=new URL(route.request().url());
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/auto_editions/onboarding.html','utf8')});
  if(u.pathname.endsWith('/approve')){approvals++;assert.equal(route.request().postDataJSON().product_gid,'p');rows[0].status='Cloud Ready';return route.fulfill({json:{status:'Cloud Ready'}});}
  if(u.pathname.endsWith('/retry')){retries++;return route.fulfill({json:{ok:true}});}
  if(u.pathname.endsWith('/onboarding'))return route.fulfill({json:{rows,mapped:284,host:{connected:0,last_seen:null}}});
  return route.fulfill({status:404});
 });
 const page=await context.newPage();await page.goto('https://onboarding.local.test/');await page.getByText('Visual review required',{exact:true}).waitFor();
 assert((await page.locator('#summary').innerText()).includes('284 mapped products'));
 assert.equal(await page.getByRole('button',{name:'Connect preparation computer'}).isEnabled(),false);
 assert.equal(await page.getByRole('button',{name:'Approve preview downloads'}).isVisible(),false);
 await page.getByRole('button',{name:'Review prepared artwork'}).click();
 assert.equal(await page.getByRole('button',{name:'Approve preview downloads'}).isEnabled(),false);
 await page.locator('#confirm').check();await page.getByRole('button',{name:'Approve preview downloads'}).click();
 await page.getByText('Cloud Ready for preview downloads.',{exact:false}).waitFor();assert.equal(approvals,1);assert.equal(retries,0);
 assert.equal(await page.locator('#retry').isEnabled(),false);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await context.close();console.log('Onboarding responsive review passed',width);
}
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
