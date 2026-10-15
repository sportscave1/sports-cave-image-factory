const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const ctx=await browser.newContext();let confirmed;
 await ctx.route('**/*',route=>{const u=new URL(route.request().url());
 if(u.pathname==='/auto-editions/setup')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/auto_editions/setup.html','utf8')});
 if(u.pathname==='/api/auto-editions/details')return route.fulfill({json:{product_title:'Synthetic design',variant_title:'XL TEST',variant_id:'123',number:5,total:100,linked:true,current_hash:'old',candidate:{hash:'a'.repeat(64),dimensions:[8505,6012],source_dimensions:[2835,2004],upscaled:true}}});
 if(u.pathname==='/api/auto-editions/preview')return route.fulfill({status:204});
 if(u.pathname==='/api/auto-editions/approve'){confirmed=JSON.parse(route.request().postData());return route.fulfill({json:{status:'TEST READY'}});}
 return route.abort();});
 const page=await ctx.newPage();await page.goto('https://edition.test/auto-editions/setup?allocation_id=42&preparation_hash='+ 'a'.repeat(64));
 await page.getByText('Review 8505 × 6012 pixels · preview enlargement.').waitFor();
 assert(await page.getByRole('button',{name:'Approve preview layout'}).isDisabled());
 await page.getByRole('checkbox').check();await page.getByRole('button',{name:'Approve preview layout'}).click();
 await page.getByRole('link',{name:'Download JPG',exact:true}).waitFor();
 assert.equal(confirmed.expected_hash,'old');assert.equal(confirmed.confirm_test_layout,true);
 assert.equal(confirmed.preparation_hash,'a'.repeat(64));
 console.log('Setup approval regression: exact candidate dimensions, explicit quality approval and stale-layout fence.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
