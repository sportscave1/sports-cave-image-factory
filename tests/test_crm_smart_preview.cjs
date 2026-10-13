// Shared browser renderer, with synthetic facts and no network/server access.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage();await page.route('**/*',r=>r.abort());
  await page.addScriptTag({content:fs.readFileSync('components/crm_sections/preview.js','utf8')});
  const results=await page.evaluate(()=>{
   const display={image:false,title:true,price:false,limit:true,next:true,remaining:true,cta:true};
   const products=Array.from({length:12},(_,i)=>({id:'gid://shopify/Product/'+(i+1),title:'Fixture '+(i+1),status:'ACTIVE',url:'https://example.com/products/fixture-'+i,
    edition:{limit:100,next:28,sold:27,remaining:null,status:'active'}}));
   const section={id:'cat',type:'catalogue',visible:true,settings:{display,columns:2,cta:'Custom CTA'},products:[products[0]]};
   const model={resolved:{},tags:['table','tr','td','p','span'],css:[]};
   const unknown=SCPreview.sectionHtml(section,model);
   section.products[0].edition.sold=100;
   const exhausted=SCPreview.sectionHtml(section,model);
   section.products[0].edition.sold=27;section.settings.smart=true;
   model.resolved.cat={section:{settings:{smart:true}},products};
   const quantities=[undefined,1,4,8,12].map(n=>{
    section.settings.smart_count=n;
    return (SCPreview.sectionHtml(section,model).match(/Fixture \d+/g)||[]).length;
   });
   return {unknown,exhausted,quantities};
  });
  assert.match(results.unknown,/#028 \/ 100/);assert.match(results.unknown,/Custom CTA/);
  assert.doesNotMatch(results.unknown,/REMAINING|SOLD OUT/);
  assert.doesNotMatch(results.exhausted,/#028/);
  assert.deepEqual(results.quantities,[4,1,4,8,12]);
  console.log('PASS browser edition consistency, unknown remaining, CTA and smart quantities');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
