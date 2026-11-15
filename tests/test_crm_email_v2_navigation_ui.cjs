// Real shared workspace/navigation/editor with disposable database records.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const titles={abandoned:'Abandoned checkouts',welcome:'Marketing subscribers',post_purchase:'Orders',win_back:'Inactive purchasers',fulfilled:'Recipients'};
(async()=>{const b=await chromium.launch({channel:'chrome',headless:true}),report=[];
try{const p=await b.newPage({viewport:{width:1440,height:1000}});p.setDefaultTimeout(45000);
await p.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
await p.goto('http://127.0.0.1:18751/?flow=welcome&state=1');
const settled=async()=>{await p.locator('[data-testid=stApp][data-test-script-state=notRunning]').waitFor();await p.waitForTimeout(200);};
for(const kind of Object.keys(titles)){
 await p.getByRole('button',{name:kind,exact:true}).click();const summary=p.locator('summary').filter({hasText:titles[kind]});await summary.waitFor();await settled();
 if(!await summary.evaluate(e=>e.parentElement.open))await summary.click();
 const search=p.getByRole('textbox',{name:'Search and filter',exact:true});await search.waitFor();await search.fill('collector1');await search.press('Enter');await settled();
 await p.waitForTimeout(1100);
 const state=JSON.parse((await p.getByText(/^FIXTURE_STATE/).innerText()).replace('FIXTURE_STATE ',''));
 assert.ok(Object.values(state).includes('collector1'),'search checkpoint '+kind);
 const other=kind==='welcome'?'post_purchase':'welcome';
 await p.getByRole('button',{name:other,exact:true}).click();await p.locator('summary').filter({hasText:titles[other]}).waitFor();await settled();
 const at=Date.now();await p.getByRole('button',{name:kind,exact:true}).click();await summary.waitFor();await search.waitFor();await settled();
 assert.equal(await summary.evaluate(e=>e.parentElement.open),true,kind+' open retained');assert.equal(await search.inputValue(),'collector1',kind+' filter retained');
 const returnMs=Date.now()-at;
 await summary.click();await search.waitFor({state:'hidden'});await settled();
 await p.getByRole('button',{name:other,exact:true}).click();await p.locator('summary').filter({hasText:titles[other]}).waitFor();await settled();
 await p.getByRole('button',{name:kind,exact:true}).click();await summary.waitFor();await settled();assert.equal(await summary.evaluate(e=>e.parentElement.open),false,kind+' closed retained');
 assert.equal(await p.getByTestId('stException').count(),0);report.push({kind,returnMs,openClosedFilterRetained:true});console.log(JSON.stringify(report.at(-1)));
}
// Switch directly away from an edited stage: existing flush boundary must retain it.
await p.getByRole('button',{name:'welcome',exact:true}).click();await p.locator('summary').filter({hasText:titles.welcome}).waitFor();await settled();const edit=p.getByRole('button',{name:/Edit Email/}).first();await edit.waitFor();await edit.click();
const subject=p.getByRole('textbox',{name:'Subject',exact:true});await subject.waitFor();await settled();await p.waitForFunction(()=>document.querySelector('input[aria-label="Subject"]')?.value.length>0);const original=await subject.inputValue(),changed=original+' [navigation fixture]';
await subject.fill(changed);await subject.press('Tab');await settled();
await p.getByRole('button',{name:'win_back',exact:true}).click();await p.locator('summary').filter({hasText:titles.win_back}).waitFor();await settled();
await p.getByRole('button',{name:'welcome',exact:true}).click();await p.locator('summary').filter({hasText:titles.welcome}).waitFor();await settled();await edit.click();await subject.waitFor();await settled();assert.equal(await subject.inputValue(),changed);
await subject.fill(original);await subject.press('Tab');await settled();await p.getByRole('button',{name:'Flow',exact:true}).click();await edit.waitFor();
await p.setViewportSize({width:390,height:900});await settled();assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
await p.screenshot({path:'.tmp-email-v2/workspace-mobile.png',fullPage:true});
fs.writeFileSync('.tmp-email-v2/navigation.json',JSON.stringify({flows:report,draftRetained:true,mobile:true},null,2));console.log('PASS draft retained through direct flow navigation');
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
