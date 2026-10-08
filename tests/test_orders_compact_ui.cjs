const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const dir=process.env.ORDERS_ARTIFACTS;fs.mkdirSync(dir,{recursive:true});const results=[];
 for(const [width,height] of [[1920,1080],[1440,900],[1280,720],[390,844]]){
  const context=await browser.newContext({viewport:{width,height}});
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();const started=Date.now();
  await page.goto('http://127.0.0.1:8894/');await page.getByTestId('stDataFrame').waitFor();
  const table=await page.getByTestId('stDataFrame').boundingBox(),heading=await page.getByRole('heading',{name:'Orders',exact:true}).boundingBox();
  const result={width,height,tableY:table.y,headingY:heading.y,tableHeight:table.height,readyMs:Date.now()-started};
  if(process.env.ORDERS_PHASE==='after'){
   assert.equal(await page.getByText(/Orders sync automatically|fulfilment row\(s\) shown/).count(),0);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   const input=page.getByRole('textbox',{name:'Search orders',exact:true});
   await input.fill('#SC3049');await input.press('Enter');
   await page.getByTestId('stDataFrame').waitFor();
   await input.fill('');await page.getByRole('button',{name:'Search',exact:true}).click();
   await page.getByTestId('stDataFrame').waitFor();
   assert.equal(await page.getByTestId('stException').count(),0);
  }
  await page.screenshot({path:path.join(dir,`${process.env.ORDERS_PHASE}-${width}.png`),fullPage:true});
  results.push(result);await context.close();
 }
 fs.writeFileSync(path.join(dir,process.env.ORDERS_PHASE+'.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
