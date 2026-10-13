// Same editor/sequence acceptance for every trigger, disposable SQL only.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});const results=[];
try{for(const kind of ['abandoned','welcome','post_purchase','win_back','fulfilled']){
 const p=await browser.newPage({viewport:{width:1440,height:1000}});p.setDefaultTimeout(45000);
 await p.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 await p.goto('http://127.0.0.1:18751/?flow='+kind);
 const edit=p.getByRole('button',{name:/Edit Email/}).first();await edit.waitFor();
 assert.equal(await p.getByTestId('stException').count(),0);
 const start=Date.now();await edit.click();
 const subject=p.getByRole('textbox',{name:'Subject',exact:true});await subject.waitFor();await p.locator('[data-testid=stApp][data-test-script-state=notRunning]').waitFor();await p.waitForTimeout(250);const editorMs=Date.now()-start;
 const original=await subject.inputValue(),changed=original+' [unified fixture]';
 await subject.fill(changed);await subject.press('Tab');await p.waitForTimeout(500);await p.locator('[data-testid=stApp][data-test-script-state=notRunning]').waitFor();
 await p.waitForFunction(()=>document.querySelectorAll('.st-key-toolbar-save button').length===1);const save=p.locator('.st-key-toolbar-save').getByRole('button',{name:'Save draft',exact:true});if(await save.count()&&await save.isEnabled())await save.click();
 await p.waitForTimeout(500);await p.getByRole('button',{name:'Flow',exact:true}).click();await edit.waitFor();
 await edit.click();await subject.waitFor();assert.equal(await subject.inputValue(),changed);
 await p.setViewportSize({width:390,height:900});await p.waitForTimeout(300);
 assert.equal(await p.getByTestId('stException').count(),0);
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
 await subject.fill(original);await subject.press('Tab');await p.waitForTimeout(500);await p.locator('[data-testid=stApp][data-test-script-state=notRunning]').waitFor();
 if(await save.count()&&await save.isEnabled())await save.click();
 await p.waitForTimeout(300);await p.getByRole('button',{name:'Flow',exact:true}).click();await edit.waitFor();
 assert.equal(await p.getByTestId('stException').count(),0);
 results.push({kind,editorMs,saveReload:true,mobile:true});console.log(JSON.stringify(results.at(-1)));await p.close();
}fs.writeFileSync('.tmp-unified-flow/editor-results.json',JSON.stringify(results,null,2));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
