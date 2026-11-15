const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch({channel:'chrome',headless:true});try{
const c=await b.newContext({viewport:{width:1440,height:1000}});await c.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
const p=await c.newPage(),errors=[];p.on('pageerror',e=>errors.push(e.message));
await p.goto('http://127.0.0.1:8544');await p.locator('.sc-home-row').first().waitFor();
const campaignName='Workflow fixture '+Date.now();await p.getByRole('button',{name:'+ New campaign',exact:true}).click();await p.getByRole('textbox',{name:'Campaign name',exact:true}).fill(campaignName);
await p.getByRole('textbox',{name:'Subject',exact:true}).fill('Workflow subject');await p.getByRole('textbox',{name:'Preview text',exact:true}).fill('Workflow preview');
await p.getByRole('tab',{name:'Editor',exact:true}).click();const frame=p.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]');
await frame.getByRole('textbox').first().fill('<h1>Saved workflow artwork</h1><p>Customer content stays intact.</p>');await frame.getByRole('textbox').first().press('Tab');
await p.waitForFunction(()=>document.querySelector('.st-key-crm-composer-preview iframe')?.contentDocument?.body?.textContent.includes('Saved workflow artwork'));
await p.getByRole('button',{name:'Save draft',exact:true}).click();
await p.getByRole('tab',{name:'Settings',exact:true}).click();await p.getByRole('radio',{name:'Schedule',exact:true}).press('Space');await p.getByRole('textbox',{name:'Subject',exact:true}).waitFor();
await p.getByRole('button',{name:'Save draft',exact:true}).click();
await p.getByRole('button',{name:'smartphone',exact:true}).click();await p.waitForFunction(()=>![...document.querySelectorAll('[data-stale=true]')].some(e=>e.getClientRects().length));
for(const width of [1440,750,390,320]){await p.setViewportSize({width,height:1000});await p.evaluate(()=>window.scrollTo(0,0));await p.screenshot({path:`tmp/email-campaign-${width}.png`,fullPage:true});assert.equal(await p.getByTestId('stMain').evaluate(e=>e.scrollWidth>e.clientWidth+2),false,`page overflow ${width}`);}
await p.setViewportSize({width:1440,height:1000});await p.getByRole('button',{name:'← Campaigns',exact:true}).click();await p.locator('.sc-home-row').first().waitFor();
await p.getByTestId('stPopoverButton').filter({hasText:'Actions for '+campaignName}).click();await p.getByRole('button',{name:'Duplicate',exact:true}).click();await p.getByRole('textbox',{name:'Subject',exact:true}).waitFor();
assert.equal(await p.getByRole('textbox',{name:'Subject',exact:true}).inputValue(),'Workflow subject');
await p.reload();await p.getByRole('textbox',{name:'Subject',exact:true}).waitFor();assert.equal(await p.getByRole('textbox',{name:'Subject',exact:true}).inputValue(),'Workflow subject');
assert.equal(await p.getByTestId('stException').count(),0);assert.deepEqual(errors,[]);console.log('PASS Campaign create/edit/save/schedule draft, responsive toolbar/preview, duplicate and reload; no send action invoked');
}finally{await b.close()}})().catch(e=>{console.error(e);process.exitCode=1});
