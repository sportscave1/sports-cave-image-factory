const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{for(const width of [1280,390]){
 const page=await browser.newPage({viewport:{width,height:800}});let stage='Recovering',reads=0;
 await page.route('**/*',route=>{const u=new URL(route.request().url());
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/auto_editions/status.html','utf8')});
  if(u.pathname==='/api/auto-editions/status'){reads++;return route.fulfill({json:{companion_connected:true,rows:[{status:stage,icon:'',checkpoint:'Owned lease',checkpoint_at:'synthetic',reason:'Synthetic '+stage,companion_status:'Companion Connected',actions:[]}]}});}
  return route.abort();
 });
 await page.goto('https://reliability.local.test/?product_gid=gid%3A%2F%2Fshopify%2FProduct%2F987&allocation_id=679');
 await page.locator('#stage').getByText('Recovering',{exact:false}).waitFor();
 assert.equal(await page.locator('#download-jpg').count(),0);
 stage='Uploading';await page.getByRole('button',{name:'Refresh',exact:true}).click();await page.locator('#stage').getByText('Uploading',{exact:false}).waitFor();
 stage='Needs Review';await page.getByRole('button',{name:'Refresh',exact:true}).click();await page.locator('#stage').getByText('Needs Review',{exact:false}).waitFor();assert.equal(await page.locator('#download-jpg').count(),0);
 stage='Cloud Ready';await page.getByRole('button',{name:'Refresh',exact:true}).click();await page.getByRole('link',{name:'Download JPG'}).waitFor();assert.equal(await page.getByRole('link',{name:'Download JPG'}).getAttribute('href'),'/auto-editions/download?allocation_id=679');
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 fs.mkdirSync('output/reliability',{recursive:true});await page.screenshot({path:`output/reliability/status-${width}.png`});
 assert.equal(reads,4);await page.close();console.log(`Recovery/Uploading/Review/download gate passed ${width}`);
 }}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
