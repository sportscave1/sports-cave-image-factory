const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('windows-upload-companion/composer.js','utf8');
const progress=source.slice(source.indexOf('  function projectProgress()'),source.indexOf('  function watchStaffResponse()'));
function read(generating,text,alert='') {
  const body={innerText:text,matches:()=>false};
  const document={querySelector:()=>generating?{}:null,querySelectorAll:selector=>selector==='[role="alert"]'?
    [{innerText:alert,getClientRects:()=>[{}]}]:[body]};
  return vm.runInNewContext(progress+';projectProgress()', {document,ad:false,design:false,location:{href:'https://chatgpt.com/c/fixture'}});
}
test('generation takes precedence over old blocker text and transient error alerts',()=>{
  const status=read(true,'SC_UPLOAD_BLOCKED: SHOPIFY','Something went wrong');
  assert.equal(status.blocked,false);assert.equal(status.generating,true);assert.equal(status.finished,false);
});
test('completed explicit Shopify failure remains actionable',()=>{
  const status=read(false,'SC_UPLOAD_BLOCKED: SHOPIFY');
  assert.equal(status.blocked,true);assert.match(status.reason,/SHOPIFY/);
});
test('ordinary completed response is pending verification, not failure',()=>{
  assert.equal(read(false,'Product is published. Companion handoff pending.').blocked,false);
});
