// Standalone synthetic HTTP fixture only. No application startup or live accounts.
const {chromium}=require('playwright'),fs=require('node:fs'),http=require('node:http'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const reports=JSON.parse(execFileSync('python',['-B','-c',`
import json
from auto_editions_resolution import for_job
def report(source,scale):
 dimensions=[n*scale for n in source]
 job=dict(manifest=dict(source_dimensions=source,dimensions=dimensions,preparation_geometry=dict(scale=scale,method='native' if scale==1 else 'photoshop_layered_bicubic_smoother')),archive_labels=dict(variant_title='Black / XL'))
 return for_job(job,dict(dimensions=dimensions,test_only=True,ppi_metadata=[300,300],print_ready=False))
print(json.dumps([report([7016,4961],1),report([2835,2004],4),report([9933,7016],1)]))
`],{encoding:'utf8'}));
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});let server;
 try{
  let info=reports[0],downloads=0,starts=0,locationReads=0;
  const job='a'.repeat(64),folder='/Synthetic/Generated/TEST',bytes=Buffer.from('synthetic full original JPEG bytes');
  const item={id:'id:exact',path:folder+'/unchanged-059-TEST.jpg',name:'unchanged-059-TEST.jpg',tag:'file',kind:'image',extension:'jpg',type:'JPEG image',revision:'rev',size:bytes.length};
  const other={...item,id:'id:other',path:folder+'/other.jpg',name:'other.jpg'};
  server=http.createServer((req,res)=>{
   const u=new URL(req.url,'http://localhost');const reply=(body,type='application/json',headers={})=>{res.writeHead(200,{'Content-Type':type,...headers});res.end(type==='application/json'?JSON.stringify(body):body);};
   if(u.pathname==='/download')return reply(fs.readFileSync('components/auto_editions/download.html'),'text/html');
   if(u.pathname==='/files-window')return reply(fs.readFileSync('components/files_window/index.html'),'text/html');
   if(u.pathname==='/files-original-actions.js')return reply(fs.readFileSync('components/files_original_actions.js'),'application/javascript');
   if(u.pathname==='/api/auto-editions/start'){starts++;return reply({job_id:job,status:'Ready',test_only:true});}
   if(u.pathname==='/api/auto-editions/state')return reply({job_id:job,status:'Ready',filename:item.name,resolution_info:info});
   if(u.pathname==='/api/auto-editions/location'){locationReads++;return reply({file_id:item.id,revision:'rev',folder_path:folder,path:item.path,resolution_info:info});}
   const listing={root_path:'/Synthetic',current_path:folder,items:[item,other],cache_namespace:'synthetic',cached_for_seconds:180};
   if(u.pathname==='/api/files-resolve')return reply({...listing,item});
   if(u.pathname==='/api/files-list')return reply(listing);
   if(u.pathname==='/api/auto-editions/file'){
    downloads++;assert.equal(u.searchParams.get('job_id'),job);
    return reply(bytes,'image/jpeg',{'Content-Disposition':'attachment; filename="'+item.name+'"','Set-Cookie':'sc-jpg-'+u.searchParams.get('download_token')+'=started; Path=/; SameSite=Strict'});
   }
   res.writeHead(404);res.end();
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`;
  fs.mkdirSync('output/resolution',{recursive:true});
  for(const width of [1280,390]){
   const context=await browser.newContext({viewport:{width,height:850},acceptDownloads:true});
   for(let index=0;index<reports.length;index++){
    info=reports[index];const page=await context.newPage();page.setDefaultTimeout(10000);
    const completed=page.waitForEvent('download');await page.goto(origin+'/download?allocation_id=42');
    const download=await completed;
    assert.equal(download.suggestedFilename(),item.name);
    assert.deepEqual(fs.readFileSync(await download.path()),bytes);
    await page.locator('#resolution:not([hidden])').waitFor();
    assert((await page.locator('#resolution-summary').innerText()).includes(info.summary));
    assert((await page.locator('#certification').innerText()).includes('TEST / NOT PRINT READY'));
    await page.waitForFunction(()=>document.getElementById('download').getAttribute('aria-disabled')==='false');
    if(index===1)assert((await page.locator('#resolution-summary').innerText()).includes('4× enlargement'));
    await page.locator('#resolution summary').click();
    assert((await page.locator('#resolution-details').innerText()).includes('DPI metadata 300 × 300'));
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    if(index<2)await page.screenshot({path:`output/resolution/download-${index}-${width}.png`});
    await page.goto(origin+'/files-window?edition_allocation=42&edition_job='+job);
    await page.locator('.file-item.selected').waitFor();await page.locator('#editionResolution:not([hidden])').waitFor();
    assert((await page.locator('#editionResolutionSummary').innerText()).includes(info.summary));
    // Exercise the existing actual copy selector; it must choose archived original.
    await page.evaluate(async()=>{window.FilesOriginal.copy=async items=>{window.copiedUrl=items[0].url;};await copyOriginalFiles([state.items.find(i=>i.id===savedEditionId)]);});
    const copied=new URL(await page.evaluate(()=>window.copiedUrl),origin);
    assert.equal(copied.pathname,'/api/auto-editions/file');assert.equal(copied.searchParams.get('job_id'),job);
    assert(!copied.pathname.includes('preview'));
    // The current Files view uses a hidden iframe for the exact original.
    // Verify its actual request; the download page above verifies response bytes.
    const savedDownload=page.waitForEvent('download');await page.getByRole('button',{name:'Download Original',exact:true}).click();
    const exact=await savedDownload;assert.deepEqual(fs.readFileSync(await exact.path()),bytes);
    await page.locator('#editionResolution summary').click();
    assert((await page.locator('#editionResolutionNotes').innerText()).includes('actual uploaded asset, crop and zoom remain unverified'));
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    const bounds=await page.locator('#editionResolution').boundingBox();
    assert(bounds.y>=0 && bounds.y+bounds.height<=850-26,'Information must remain inside the viewport above the status bar');
    if(index<2)await page.screenshot({path:`output/resolution/files-${index}-${width}.png`,style:'#toast{visibility:hidden!important}'});
    await page.locator('.file-item[data-path="'+other.path+'"]').click();
    assert.equal(await page.locator('#editionResolution').isVisible(),false);
    await page.close();
   }
   await context.close();
  }
  assert.equal(starts,6);assert.equal(locationReads,6);assert.equal(downloads,12);
  console.log('6 desktop/mobile scenarios passed: native below recommendation, enlarged, sufficient; TEST/crop labels, original download bytes, copy selection and stale-selection isolation.');
 }finally{await browser.close();if(server){server.closeAllConnections();await new Promise(r=>server.close(r));}}
})().catch(e=>{console.error(e);process.exitCode=1;});
