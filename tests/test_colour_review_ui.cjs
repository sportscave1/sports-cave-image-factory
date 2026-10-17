// Isolated browser fixture. No credentials, live policy or original PSD access.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const pid='gid://shopify/Product/987',source={product_gid:pid,file_id:'id:synthetic',revision:'a1',content_hash:'a'.repeat(64)};
const review={source,review_hash:'pinned-review',matching_policy:null,matching_reason:'Missing verified source-group membership.',requirements:['Verify independent designer/export lineage.','Review trusted colour-managed comparisons.'],candidates:[{group:'previously-approved-group',approval_hash:'approved-reference',profile:{description:'sRGB IEC61966-2.1'},scope:{kind:'exact_revision',members:56}}]};
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 for(const width of [1280,390]){
  const page=await browser.newPage({viewport:{width,height:850},acceptDownloads:true});let submissions=0,approvals=0,stale=false;const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>{const u=new URL(r.request().url());
   if(u.pathname==='/auto-editions/status')return r.fulfill({contentType:'text/html',body:fs.readFileSync('components/auto_editions/status.html','utf8')});
   if(u.pathname==='/auto-editions/colour-review')return r.fulfill({contentType:'text/html',body:fs.readFileSync('components/auto_editions/colour-review.html','utf8')});
   if(u.pathname==='/api/auto-editions/status')return r.fulfill({json:{rows:[{product_gid:pid,status:'Needs Review',reason:'Colour policy awaiting approval',actions:['colour-review']}]}});
   if(u.pathname.endsWith('/colour'))return r.fulfill({json:review});
   if(u.pathname.endsWith('/colour-proposal')){
    submissions++;const b=r.request().postDataJSON();assert.equal(b.review_hash,'pinned-review');assert.equal(b.reference_policy,'approved-reference');assert.equal(b.workflow_scope,true);assert.match(b.provenance.sha256,/^[a-f0-9]{64}$/);assert(!JSON.stringify(b).includes('independent designer manifest fixture'));
    return r.fulfill({status:stale?409:200,json:stale?{error:'Source or policy registry changed. Refresh and review again.'}:{proposal:{schema:2,source,status:'awaiting_approval'},reviewed_hash:'exact-proposal-hash',applied:false,next_action:'Offline owner review required. No policy applied.'}});
   }
   if(u.pathname.endsWith('/colour-approve')){approvals++;assert.equal(r.request().postDataJSON().reviewed_hash,'exact-proposal-hash');return r.fulfill({json:{ok:true,resumed:true}});}
   throw Error('Unexpected route '+u.pathname);
  });
  await page.goto('https://colour.local.test/auto-editions/status?product_gid='+encodeURIComponent(pid));
  await page.getByRole('button',{name:'Review colour profile',exact:true}).click();
  const frame=page.frameLocator('#review');await frame.locator('#form').waitFor();
  assert((await frame.locator('#source').innerText()).includes(source.content_hash));
  assert.match(await frame.locator('#state').innerText(),/Missing verified/);
  await frame.locator('#workflow').fill('verified-workflow');await frame.locator('#default').check();
  const fixture={name:'evidence.txt',mimeType:'text/plain',buffer:Buffer.from('independent designer manifest fixture')};
  for(const name of ['provenance','references','comparisons'])await frame.locator('#'+name).setInputFiles(fixture);
  fs.mkdirSync('output/colour-reuse',{recursive:true});await page.screenshot({path:'output/colour-reuse/review-'+width+'.png',fullPage:true});
  const pending=page.waitForEvent('download');await frame.getByRole('button',{name:'Prepare proposal for owner review'}).click();const download=await pending;
  const value=JSON.parse(fs.readFileSync(await download.path(),'utf8'));assert.equal(value.status,'awaiting_approval');assert.equal(submissions,1);
  await frame.locator('#result').filter({hasText:'awaiting owner approval'}).waitFor();
  stale=true;await frame.getByRole('button',{name:'Prepare proposal for owner review'}).click();
  await frame.locator('#result').filter({hasText:'Source or policy registry changed'}).waitFor();assert.equal(submissions,2);
  await frame.locator('#ownerDecision').check();await frame.locator('#approve').click();await frame.locator('#result').filter({hasText:'Resume queued for this exact source'}).waitFor();assert.equal(approvals,1);
  assert(await frame.locator('body').evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
  await page.close();
 }
 console.log('PASS desktop/mobile actionable colour review, pinned source, evidence hashing without uploads, pinned proposal, explicit approval/resume, stale-source refusal.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
