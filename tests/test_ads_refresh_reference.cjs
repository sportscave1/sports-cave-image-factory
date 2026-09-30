const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('components/ads_refresh_reference/index.html','utf8');
async function check(mime,{secure=true,supported=true,denied=false}={}) {
  const data=Buffer.from('unchanged archived source');
  const elements={copy:{addEventListener:(_event,fn)=>elements.click=fn},open:{focus(){this.focused=true;}},status:{}};
  let original,canvas,draws=0,writes=0,copied;
  const context={Uint8Array,Blob,atob,window:{isSecureContext:secure},
    URL:{createObjectURL:blob=>{original=blob;return 'blob:original';}},
    document:{getElementById:id=>elements[id],createElement:tag=>{
      assert.equal(tag,'canvas');canvas={getContext:()=>({drawImage:(_image,x,y)=>{assert.equal(x,0);assert.equal(y,0);draws++;}}),toBlob:(resolve,type)=>{assert.equal(type,'image/png');resolve(new Blob(['lossless-pixels'],{type}));}};return canvas;}},
    Image:class {naturalWidth=4096;naturalHeight=2731;async decode(){}},
    ClipboardItem:class {constructor(items){this.items=items;}},
    navigator:{clipboard:supported?{write:async items=>{writes++;copied=await items[0].items['image/png'];if(denied)throw Error('denied');}}:undefined}};
  vm.createContext(context);
  const script=html.slice(html.indexOf('<script>')+8,html.indexOf('</script>')).replace('__WINNING_IMAGE__',JSON.stringify({mime,base64:data.toString('base64')}));
  vm.runInContext(script,context);
  assert.equal(writes,0,'clipboard must wait for click');
  assert.equal(elements.open.href,'blob:original');
  assert.deepEqual(Buffer.from(await original.arrayBuffer()),data);
  await elements.click();
  if(!secure||!supported||denied){assert.match(elements.status.textContent,/right-click/);assert.equal(elements.open.focused,true);}
  else{assert.match(elements.copy.textContent,/Copied/);assert.equal(copied.type,'image/png');}
  if(secure&&supported){
    if(mime==='image/png'){assert.equal(draws,0);assert.equal(copied,original);}
    else{assert.equal(draws,1);assert.equal(canvas.width,4096);assert.equal(canvas.height,2731);}
  }
  assert.deepEqual(Buffer.from(await original.arrayBuffer()),data,'original fallback bytes must never change');
}
(async()=>{await check('image/png');await check('image/jpeg');await check('image/webp');await check('image/png',{denied:true});await check('image/jpeg',{supported:false});await check('image/jpeg',{secure:false});console.log('Winning image clipboard checks passed: original bytes, PNG passthrough, natural-resolution conversion, success, denied, unsupported and insecure fallbacks.');})().catch(error=>{console.error(error);process.exitCode=1;});
