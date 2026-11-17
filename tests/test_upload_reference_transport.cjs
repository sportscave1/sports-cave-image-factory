const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const crypto=require('node:crypto');
const source=fs.readFileSync(require('node:path').join(__dirname,'../components/product_upload_gallery/app.js'),'utf8');
const start=source.indexOf('  async function referenceFile(');
const end=source.indexOf('  function companionRequest(',start);
const bytes=Buffer.from('exact saved black-frame WebP');
const descriptor={url:'/api/product-uploads/asset?token=fixture',name:'black.webp',type:'image/webp',size:bytes.length,
  sha256:crypto.createHash('sha256').update(bytes).digest('hex')};
let calls=[],body=bytes,statuses=[];
const context=vm.createContext({URL,Uint8Array,Number,Error,crypto:crypto.webcrypto,btoa,
  location:{origin:'https://sports-cave-image-factory.onrender.com'},controller:new AbortController(),active:()=>{},
  fetch:async(url,options)=>{calls.push({url,options});const status=statuses.shift()||200;return {
    ok:status===200,status,arrayBuffer:async()=>Uint8Array.from(body).buffer};}});
vm.runInContext(source.slice(start,end)+'\nglobalThis.compatible=supportsReference;',context);
async function main(){
  assert.equal(context.compatible('1.3.2'),false);
  assert.equal(context.compatible('1.3.3'),true);
  assert.equal(context.compatible('1.4.0'),true);
  assert.equal(context.compatible(undefined),false);
  const actual=await context.referenceFile(descriptor,1);
  assert.equal(actual.url,undefined);
  assert.equal(actual.data,bytes.toString('base64'));
  assert.equal(actual.sha256,descriptor.sha256);
  assert.equal(calls[0].url,'https://sports-cave-image-factory.onrender.com'+descriptor.url);
  assert.equal(calls[0].options.credentials,'same-origin');
  await assert.rejects(()=>context.referenceFile({...descriptor,url:'https://download.dropbox.com/file'},1),/Invalid/);
  assert.equal(calls.length,1);
  body=Buffer.from('wrong original');
  await assert.rejects(()=>context.referenceFile(descriptor,1),/verification/);
  body=bytes;statuses=[503,200];calls=[];
  await context.referenceFile(descriptor,1);
  assert.equal(calls.length,2);
  statuses=[403];calls=[];
  await assert.rejects(()=>context.referenceFile(descriptor,1),/unavailable/);
  assert.equal(calls.length,1);
  console.log('Verified original transport: authenticated OS origin, exact bytes, capability, corruption and retry checks passed.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
