// Synthetic visualizer action hooks. No browser network or production writes.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
function fixture({offline=false,mobile=true}={}) {
 const posts=[],local=[],storage=new Map(),metadata={product_id:'123',variant_id:'456',frame:'Black',size:'Medium',unit:'cm',product_title:'Artwork',customer_email:'private@example.test'};
 let downloads=0;
 const window={dispatchEvent:e=>local.push(e)};
 const fetch=(url,options)=>{
   if(url.includes('/analytics/')){posts.push(JSON.parse(options.body));return offline?Promise.reject(new Error('offline')):Promise.resolve({ok:true});}
   return Promise.resolve({ok:true,json:async()=>({ok:true,preview_id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',preview_token:'secret'})});
 };
 vm.runInNewContext(fs.readFileSync('docs/storefront/wall-preview-crm-v2.js','utf8'),{window,fetch,crypto,Date,URL,URLSearchParams,Blob,File,AbortController,
  sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
  location:{href:'https://sportscaveshop.com/products/a?utm_source=test&email=private'},document:{referrer:'https://search.test/?q=private'},
  navigator:{share:async()=>{},canShare:()=>false},matchMedia:()=>({matches:mobile}),
  CustomEvent:class{constructor(name,{detail}){this.name=name;this.detail=detail;}},setTimeout,clearTimeout});
 const adapter=window.SportsCaveWallPreviewCRM({metadata:()=>metadata,compositeBlob:async()=>new Blob(['composite']),showActions:()=>{},showConfirm:()=>{},archiveStatus:()=>{},downloadBlob:()=>downloads++});
 return {adapter,posts,local,metadata,downloads:()=>downloads};
}
(async()=>{
 for(const mobile of [true,false])for(const source of ['camera','upload']) {
  const f=fixture({mobile});const a=f.adapter;
  a.opened();source==='camera'?a.cameraOpened():a.galleryOpened();a.newWallPhoto();
  source==='camera'?a.photoCaptured():a.photoUploaded();a.photoReady();a.photoReady();
  a.dragCompleted(0);a.dragCompleted(8);a.dragCompleted(10);
  a.frameChanged('Black');f.metadata.frame='White';a.frameChanged('White');a.frameChanged('White');
  a.sizeChanged('Medium');f.metadata.size='XL';a.sizeChanged('XL');a.sizeChanged('XL');
  a.scaleStarted();a.scaleCompleted();a.quickPreviewUsed();
  await a.confirm();await a.download();await a.share();a.addedToCart();a.checkoutStarted();a.checkoutStarted();a.closed();
  await Promise.resolve();
  const names=f.posts.map(p=>p.event);
  for(const suffix of ['Started','PhotoReady','ArtworkDragged','FrameChanged','SizeChanged','ScaleStarted','ScaleCompleted','QuickPreviewUsed','Confirmed','Downloaded','Shared','AddedToCart','CheckoutStarted','Closed'])assert.equal(names.filter(n=>n==='WallPreview'+suffix).length,1,suffix);
  assert.ok(names.includes('WallPreview'+(source==='camera'?'PhotoCaptured':'PhotoUploaded')));
  assert.ok(f.posts.every(p=>p.device_type===(mobile?'mobile':'desktop')));
  assert.equal(f.posts.at(-1).furthest_stage,'CheckoutStarted');
  assert.equal(f.posts.at(-1).capture_source,source);
  assert.ok(f.posts.every(p=>!JSON.stringify(p).includes('private')));
  assert.ok(f.local.every(e=>!('session_id' in e.detail)));
  assert.equal(new Set(f.posts.map(p=>p.client_preview_id)).size,1);
  assert.equal(f.downloads(),1);assert.ok(a.cartProperties()._wall_preview_id);
 }
 const f=fixture({offline:true});f.adapter.opened();f.adapter.newWallPhoto();await f.adapter.confirm();
 await f.adapter.download();f.adapter.addedToCart();await Promise.resolve();assert.equal(f.downloads(),1);
 assert.ok(f.adapter.cartProperties()._wall_preview_id);
 console.log('PASS: 4 anonymous camera/upload/mobile/desktop journeys; event dedupe; privacy; complete action hooks; analytics outage isolation');
})().catch(e=>{console.error(e);process.exitCode=1});
