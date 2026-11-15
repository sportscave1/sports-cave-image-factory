// Local browser only. Run scripts/verify_frame_banner.py first for public assets.
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert');
const root=path.resolve('artifacts/frame-banner');
const examples=JSON.parse(fs.readFileSync(path.join(root,'examples.json'),'utf8'));
const js=fs.readFileSync('tests/fixtures/wall_banner/sports-cave-wall-artwork.js','utf8');
const server=http.createServer((req,res)=>{
 const file=path.resolve(root,'.'+decodeURIComponent(req.url.split('?')[0]));
 if(!file.startsWith(root+path.sep)||!fs.existsSync(file)){res.writeHead(404).end();return;}
 const ext=path.extname(file);res.setHeader('Content-Type',ext==='.html'?'text/html; charset=utf-8':ext==='.jpg'?'image/jpeg':'image/png');
 res.end(fs.readFileSync(file));
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try {
 const page=await browser.newPage({viewport:{width:1000,height:900}});const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/'+examples[0].filename.replace(/-black$/,'')+'-email.html');
 await page.setContent('<style>body{font:14px Arial;background:#eee}article{margin:12px;padding:12px;background:white}.pair{display:flex;gap:16px}.pair>div{width:46%}canvas,img{width:100%;height:auto}</style><h1>Shopify canvas / server crop</h1>');
 await page.addScriptTag({content:js});
 const results=await page.evaluate(async({examples,base})=>{
  const results=[];
  for(const sample of examples){
   const article=document.createElement('article');const h=document.createElement('h2');h.textContent=sample.name+(sample.exact_source_match?' — source verified':' — crop reference only; email retains original image');article.append(h);
   const pair=document.createElement('div');pair.className='pair';const left=document.createElement('div'),right=document.createElement('div');pair.append(left,right);article.append(pair);document.body.append(article);
   const root=document.createElement('div');for(const frame of ['black','oak','white'])root.setAttribute('data-'+frame+'-url',base+'/'+sample.filename+'-source.png');
   const canvas=await window.SportsCaveWallArtwork.render(root,sample.frame);left.append(canvas);
   const image=new Image();image.src=base+'/'+sample.filename+'-crop.jpg';await image.decode();right.append(image);
   const reference=document.createElement('canvas');reference.width=image.naturalWidth;reference.height=image.naturalHeight;
   const ctx=reference.getContext('2d');ctx.drawImage(canvas,0,0,reference.width,reference.height);const a=ctx.getImageData(0,0,reference.width,reference.height).data;
   ctx.drawImage(image,0,0);const b=ctx.getImageData(0,0,reference.width,reference.height).data;let error=0;
   for(let i=0;i<a.length;i++){if(i%4!==3)error+=Math.abs(a[i]-b[i]);}
   results.push({name:sample.name,mean_rgb_error:error/(a.length*0.75),width:image.naturalWidth,height:image.naturalHeight});
  }return results;
 },{examples,base});
 for(const row of results)assert(row.mean_rgb_error<10,JSON.stringify(row));
 await page.screenshot({path:path.join(root,'shopify-vs-server.png'),fullPage:true});
 for(const width of [1000,375]){
  await page.setViewportSize({width,height:900});await page.goto(base+'/peter-brock-bathurst-wall-art-email.html');
  await page.locator('img').evaluate(img=>img.decode());
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  const href=await page.getByRole('link',{name:'PREVIEW IN MY CAVE'}).getAttribute('href');assert(href.includes('variant=')&&href.includes('sc_wall_preview=1'));
  await page.screenshot({path:path.join(root,'email-'+width+'.png'),fullPage:true});
 }
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(root,'visual-results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify({comparisons:results.length,maxMeanRgbError:Math.max(...results.map(r=>r.mean_rgb_error)),viewports:[1000,375]}));
 } finally {await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
