/* Synthetic browser bridge and HTTP responses; no live services or desktop actions. */
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const source=fs.readFileSync('components/psd_open/index.html','utf8');
  for(const owner of [false,true]){
   const page=await browser.newPage();const calls=[];
   await page.addInitScript(()=>{
    window.nativeMessages=[];window.created=[];window.revoked=[];
    const create=URL.createObjectURL.bind(URL),revoke=URL.revokeObjectURL.bind(URL);
    URL.createObjectURL=blob=>{const url=create(blob);created.push(url);return url;};
    URL.revokeObjectURL=url=>{revoked.push(url);revoke(url);};
    window.chrome=window.chrome||{};window.chrome.webview={postMessage:m=>nativeMessages.push(m),addEventListener(){},removeEventListener(){}};
   });
   await page.route('**/*',route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!=='http://staff.test')return route.abort();
    if(request.method()==='GET')return route.fulfill({contentType:'text/html',body:source.replace('__OWNER_DESKTOP_ALLOWED__',String(owner))});
    const action=request.postDataJSON().action;calls.push(action);
    if(action==='preview')return route.fulfill({contentType:'image/jpeg',body:Buffer.from([255,216,255,217])});
    return route.fulfill({json:{ok:true,name:'Synthetic.psd',dropbox_url:'http://staff.test/dropbox',mac_url:''}});
   });
   await page.goto('http://staff.test/api/files-psd-open?product_gid=synthetic');
   await page.waitForTimeout(250);
   assert.deepEqual(calls,[]);assert.deepEqual(await page.evaluate(()=>nativeMessages),[]);
   if(!owner){assert(await page.locator('#app').isHidden());await page.evaluate(()=>app());assert.deepEqual(await page.evaluate(()=>nativeMessages),[]);}
   assert.equal(await page.locator('#download').getAttribute('href'),'/api/files-psd-original?product_gid=synthetic');
   await page.locator('#artwork').click();await page.waitForFunction(()=>created.length===1);
   assert.deepEqual(calls,['preview']);await page.evaluate(()=>SportsCavePsdDismiss());
   assert.deepEqual(await page.evaluate(()=>revoked),await page.evaluate(()=>created));
   assert.deepEqual(await page.evaluate(()=>nativeMessages),[]);
   console.log(`PSD_SYNTHETIC owner=${owner} idle_api_requests=0 desktop_messages=0 preview_click_requests=1 retained_preview_urls=0`);
   await page.close();
  }
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
