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
test('ad missing-file marker retains the reported provider rejection',()=>{
  const result=progress('The provider returned moderation_blocked.\nSC_AD_BLOCKED: architectural-wall.jpg is missing.',false,'6a6bd98cd6f081918788b544dcdecfc2');
  assert.equal(result.blocked,true);assert.match(result.reason,/moderation_blocked/);
  assert.match(result.reason,/architectural-wall.jpg/);
});
test('does not apply upload fallback to Design',()=>{
  assert.equal(progress('moderation_blocked; pending publication',false,'6a1e449948e881919c1e345006d63654').blocked,false);
});
const designProject='6a1e449948e881919c1e345006d63654';
const hamilton='Silver & Soul remains at its original Review revision. The image service rejected the generation. The editing workspace disconnected before I could inspect the layers or save a provisional finish. The grungier treatment, replacement PSD and updated JSON are still pending.';
test('Hamilton completed rejection releases immediately without a status marker',()=>{
  assert.equal(progress(hamilton,false,designProject).blocked,true);
  assert.equal(progress(hamilton,true,designProject).blocked,false);
});
test('cancelled generation with unfinished delivery is a terminal design blocker',()=>{
  assert.equal(progress('The generation was cancelled. The replacement PSD is still pending.',false,designProject).blocked,true);
});
test('review-only concerns and repaired failures do not release a design',()=>{
  for(const text of ['The generation was rejected earlier. The replacement PSD and updated JSON were delivered. Review is pending.',
    'Sponsor lettering is unverified. The updated JSON is pending.',
    'The replacement PSD and updated JSON were delivered to Review.'])
    assert.equal(progress(text,false,designProject).blocked,false,text);
});
test('design watcher wakes after stable completion and tolerates invalidated extension context',async()=>{
  let tick,listener;const messages=[];
  const chrome={runtime:{id:'test',onMessage:{addListener(fn){listener=fn;}},sendMessage:async message=>{messages.push(message);return {accepted:true};}}};
  vm.runInNewContext(source,{chrome,location:{href:`https://chatgpt.com/g/g-p-${designProject}/c/01234567-0123-0123-0123-0123456789ab`},
    document:{querySelector:()=>null,querySelectorAll:s=>s.includes('data-message-author-role')?[{innerText:hamilton,matches:()=>false}]:[]},
    setInterval(fn,ms){assert.equal(ms,1500);tick=fn;return 1;},setTimeout(){return 2;},clearInterval(){}});
  tick();assert.equal(messages.length,0);tick();await Promise.resolve();assert.equal(messages.length,1);
  tick();assert.equal(messages.length,1);
  chrome.runtime=undefined;assert.doesNotThrow(()=>tick());
});
