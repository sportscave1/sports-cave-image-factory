// Immediate layout edits use Python's shared formatter; all browser requests blocked.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const cases=JSON.parse(execFileSync(process.env.CRM_TEST_PYTHON||'python',['-B','-c',
 'import json; from tests.test_crm_collection_display_titles import CASES; print(json.dumps(CASES))'],{encoding:'utf8'}));
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage();await page.route('**/*',r=>r.abort());
  await page.addScriptTag({content:fs.readFileSync('components/crm_sections/preview.js','utf8')});
  const results=await page.evaluate(cases=>{
   const model={resolved:{},tags:['table','tr','td','p','span'],css:[],catalogue_titles:Object.fromEntries(cases)};
   return cases.map(([title,expected])=>{
    const product={id:'gid://shopify/Product/1',title,status:'ACTIVE',url:'https://example.test/products/wall-art',
     edition:{limit:100,next:37,sold:36,remaining:64,status:'active'}};
    const section={id:'cat',type:'catalogue',visible:true,products:[product],settings:{cta:'Claim Your Edition',
     display:{image:false,title:true,price:false,limit:true,next:true,remaining:true,cta:true}}};
    const before=JSON.stringify(section);
    const manual=SCPreview.sectionHtml(section,model);
    const unchanged=JSON.stringify(section)===before;
    section.settings.smart=true;model.resolved.cat={section:{settings:{smart:true}},products:[product]};
    const smart=SCPreview.sectionHtml(section,model);
    section.settings.display.title=false;
    const hidden=SCPreview.sectionHtml(section,model);
    const text=html=>{const node=document.createElement('div');node.innerHTML=html;return node.textContent};
    return {expected,manual:text(manual),smart:text(smart),hidden:text(hidden),unchanged};
   });
  },cases);
  for(const r of results){
   for(const output of [r.manual,r.smart]){
    assert.ok(output.startsWith(r.expected),JSON.stringify(r));
    assert.match(output,/#037 \/ 100/);assert.match(output,/64 REMAINING/);assert.match(output,/Claim Your Edition/);
   }
   assert.ok(!r.hidden.startsWith(r.expected));assert.equal(r.unchanged,true);
  }
  console.log(`PASS ${cases.length} manual and Smart Collection titles, title toggle, edition facts and unchanged product data`);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
