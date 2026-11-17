const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../windows-upload-companion/composer.js'), 'utf8');
function progress(text, generating = false, project = '6a387a17627081918e1700ec2783a12b') {
  let listener;
  const document = {
    querySelectorAll(selector) {return selector.includes('data-message-author-role') ? [{innerText:text,matches:()=>false}] : [];},
    querySelector() {return generating ? {} : null;},
  };
  vm.runInNewContext(source, {document, location:{href:`https://chatgpt.com/g/g-p-${project}/c/01234567-0123-0123-0123-0123456789ab`},
    chrome:{runtime:{id:'test',onMessage:{addListener(fn){listener=fn;}}}}});
  let result;
  listener({type:'project:progress'}, {id:'test'}, value=>result=value);
  return result;
}
test('recognizes observed pending publication moderation response without marker',()=>{
  const result=progress('Silver & Soul is pending publication. The image tool returned moderation_blocked for Office and Living Room. Publication and the Upload Companion handoff remain pending.');
  assert.equal(result.blocked,true);
  assert.match(result.reason,/MODERATION/);
});
test('does not mark an in-progress response blocked',()=>{
  assert.equal(progress('moderation_blocked; pending publication',true).blocked,false);
});
test('does not mistake resolved historical moderation for a current failure',()=>{
  assert.equal(progress('Earlier moderation_blocked was resolved with approved supplied assets. Publication and mapping verified.').blocked,false);
});
test('preserves existing explicit stage blockers',()=>{
  assert.match(progress('SC_UPLOAD_BLOCKED: PSD_MAPPING').reason,/PSD_MAPPING/);
});
test('does not apply upload fallback to Design',()=>{
  assert.equal(progress('moderation_blocked; pending publication',false,'6a1e449948e881919c1e345006d63654').blocked,false);
});
