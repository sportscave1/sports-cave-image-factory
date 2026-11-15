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
  await page.screenshot({path:path.join(dir,`${process.env.ORDERS_PHASE}-${width}.png`),fullPage:true});
  if(process.env.ORDERS_PHASE==='after'){
   assert.equal(await page.getByText(/Orders sync automatically|fulfilment row\(s\) shown/).count(),0);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   const canvas=await page.getByTestId('stDataFrame').locator('canvas').first().boundingBox();
   assert.ok(canvas.height<=table.height&&table.height-canvas.height<4,'Grid must resize internally, not clip its canvas');
   const inputBox=await page.getByRole('textbox',{name:'Search orders',exact:true}).boundingBox();
   assert.ok(inputBox.y>=heading.y+heading.height,'Heading must not overlap search');
   if(width===1440){
    await page.mouse.click(table.x+16,table.y+51);
    await page.getByText('1 selected',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Preview Certificate',exact:true}).click();
    await page.getByText('Fixture action on 1 selected units').waitFor();
   }
   const input=page.getByRole('textbox',{name:'Search orders',exact:true});
   await input.fill('#SC3049');await input.press('Enter');
   await page.locator('#orders-fixture-state[data-query="#SC3049"][data-count="1"]').waitFor({state:'attached'});
   await input.fill('');await page.getByTestId('stForm').getByRole('button',{name:'Search',exact:true}).click();
   await page.locator('#orders-fixture-state[data-query=""][data-count="62"]').waitFor({state:'attached'});
   assert.equal(await page.getByTestId('stException').count(),0);
  }
  results.push(result);await context.close();
 }
 fs.writeFileSync(path.join(dir,process.env.ORDERS_PHASE+'.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
