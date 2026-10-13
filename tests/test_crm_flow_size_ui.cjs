const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const b=await chromium.launch({channel:'chrome',headless:true});
 try{for(const width of [1440,390])for(const kind of ['abandoned','welcome','post_purchase','win_back','fulfilled']){
  const p=await b.newPage({viewport:{width,height:1100}});
  await p.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());
  const smart=process.env.CRM_SMART_UI==='1';
  await p.goto('http://127.0.0.1:18737/?flow='+kind+(smart?'&smart=1':''));
  await p.locator('.sc-email-size [role="progressbar"]').waitFor({timeout:30000});
  const first=await p.locator('.sc-email-size').innerText();assert.match(first,/SAFE/);
  if(smart){
   await p.frameLocator('iframe[data-testid="stIFrame"]').getByText('Artwork 3',{exact:true}).first().waitFor({timeout:30000});
  }
  const input=p.getByRole('textbox',{name:'Fixture HTML',exact:true});
  await input.fill('<p>'+('Editor size fixture '.repeat(900))+'</p>');await input.press('Tab');
  await p.waitForTimeout(1000);
  const second=await p.locator('.sc-email-size').innerText();assert.notEqual(first,second);
  await p.getByRole('button',{name:'smartphone',exact:true}).click();
  await p.waitForTimeout(250);assert.equal(await p.locator('.sc-email-size').innerText(),second);
  assert.equal(await p.locator('[data-testid="stException"]').count(),0);
  await p.screenshot({path:`.tmp-preview-performance/flow-size-${kind}-${width}.png`,fullPage:true});
  console.log(JSON.stringify({kind,width,smart,first,edited:second,mobile:true}));await p.close();
 }}finally{await b.close();}
})().catch(e=>{console.error(e);process.exit(1)});
