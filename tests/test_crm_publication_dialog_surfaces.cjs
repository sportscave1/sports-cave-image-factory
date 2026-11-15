// Both supported native dialog structures, including the production OS theme.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{for(const width of [1440,390,320])for(const aria of [false,true]){
  const page=await browser.newPage({viewport:{width,height:850}});
  await page.route('**/*',r=>r.abort());
  const content=`<h2>Publish email?</h2><div class="st-key-sc-publication-body"><span class="sc-publication-confirm" hidden></span><div class="sc-publication-summary">Selected email <span>Disabled verification flow</span></div><p>Publish this saved email.</p><div style="display:flex;gap:8px;margin-top:12px"><div class="st-key-automation-publication-cancel"><button kind="secondary">Cancel</button></div><div class="st-key-automation-publication-confirm"><button kind="primary">Publish email</button></div></div></div>`;
  await page.setContent(`<style>body{margin:0}.stDialog{display:flex;justify-content:center;padding-top:48px;background:#ddd;min-height:100vh}.st-key-sc-publication-body{padding:16px;box-sizing:border-box}[data-testid="stDialog"] button[kind="secondary"]{background:#c69737!important}[data-testid="stDialog"] button[kind="primary"]{background:#d4a54c!important}</style><div data-testid="stDialog" class="stDialog">${aria?'<div data-rac style="width:500px;min-width:min(320px,100% - 32px);background:white;box-shadow:0 4px 16px #0003"><section data-rac role="dialog">'+content+'</section></div>':'<div role="dialog">'+content+'</div>'}</div><div id="unrelated" data-testid="stDialog"><button kind="secondary">Other dialog</button></div>`);
  await page.addStyleTag({content:fs.readFileSync('components/crm_sections/publication_confirm.css','utf8')});
  await page.addScriptTag({content:fs.readFileSync('components/crm_sections/publication_confirm.js','utf8')});
  const dialog=page.getByRole('dialog'),bounds=await dialog.boundingBox();assert.ok(bounds.width<=Math.min(420,width-32));
  assert.equal(await dialog.getByRole('button',{name:'Cancel',exact:true}).evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(250, 249, 246)');
  assert.equal(await dialog.getByRole('button',{name:'Publish email',exact:true}).evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(200, 163, 70)');
  if(aria){const outer=await dialog.evaluate(e=>({width:e.parentElement.getBoundingClientRect().width,bg:getComputedStyle(e.parentElement).backgroundColor,shadow:getComputedStyle(e.parentElement).boxShadow}));assert.equal(outer.width,bounds.width);assert.equal(outer.bg,'rgba(0, 0, 0, 0)');assert.equal(outer.shadow,'none');}
  assert.equal(await page.locator('#unrelated button').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(198, 151, 55)');await page.close();
 }
 console.log('PASS single modal surface and scoped button colours in BaseWeb/React Aria at 1440/390/320px');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
