const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage();await page.route('**/*',r=>r.abort());await page.setContent('<html><body></body></html>');
 await page.addScriptTag({content:fs.readFileSync('components/crm_sections/preview.js','utf8')});
 const cases=JSON.parse(fs.readFileSync('tmp/local-editor-models.json','utf8'));
 for(const test of cases){
  const result=await page.evaluate(({section,sections,model,expected,sibling_offer})=>{
   const summarize=html=>{const host=document.createElement('div');host.innerHTML=html;return {text:host.textContent.replace(/\s+/g,' ').trim(),images:[...host.querySelectorAll('img')].map(n=>({src:n.getAttribute('src'),alt:n.getAttribute('alt')})),headings:host.querySelectorAll('strong').length};};
   if(sibling_offer){
    const hidden=structuredClone(sections);hidden.find(s=>s.type==='discount').visible=false;
    if(!SCPreview.sectionHtml(section,model,hidden).includes(model.offer.code))throw Error('Hidden creative disconnected the email offer');
    const changed=structuredClone(model);changed.offer.code='NEWCODE';changed.resolved={};
    if(!SCPreview.sectionHtml(section,changed,sections).includes('NEWCODE'))throw Error('Changed email offer reused stale rendered code');
   }
   return {actual:summarize(SCPreview.sectionHtml(section,model,sections||[section])),expected:summarize(SCPreview.sanitize(expected,model))};
  },test);
  assert.deepEqual(result.actual,result.expected,test.section.settings?.kind||test.section.type);
 }
 console.log(cases.length+' incremental composition cases match server-rendered text, images and emphasis');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
