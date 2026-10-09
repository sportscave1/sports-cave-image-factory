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
    let blocked=false;try{SCPreview.sectionHtml(section,model,hidden)}catch(e){blocked=e.message.includes('Select a verified discount')}
    if(!blocked)throw Error('Hidden sibling offer reused stale rendered discount');
    const changed=structuredClone(sections);changed.find(s=>s.type==='discount').offer.code='NEWCODE';
    if(!SCPreview.sectionHtml(section,model,changed).includes('NEWCODE'))throw Error('Changed sibling offer reused stale rendered code');
   }
   return {actual:summarize(SCPreview.sectionHtml(section,model,sections||[section])),expected:summarize(SCPreview.sanitize(expected,model))};
  },test);
  assert.deepEqual(result.actual,result.expected,test.section.settings?.kind||test.section.type);
 }
 console.log(cases.length+' incremental composition cases match server-rendered text, images and emphasis');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
