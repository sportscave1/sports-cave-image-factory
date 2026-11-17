const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');

function fixture({text='', generating=false, alert='', design=false}={}) {
  let listener, clicks=0;
  const project = design ? '6a1e449948e881919c1e345006d63654' : '6a387a17627081918e1700ec2783a12b';
  const location={href:`https://chatgpt.com/g/g-p-${project}/c/00000000-0000-0000-0000-000000000001`};
  const body={innerText:text,matches:()=>false};
  const stop={click(){clicks++;}};
  const document={querySelector:()=>generating ? stop : null,
    querySelectorAll:query=>query==='[role="alert"]' ? (alert ? [{innerText:alert,getClientRects:()=>[{}]}] : []) : [body]};
  const chrome={runtime:{id:'fixture',onMessage:{addListener:fn=>listener=fn}}};
  vm.runInNewContext(fs.readFileSync('windows-upload-companion/composer.js','utf8'),{location,document,chrome});
  return {send:(type,sender='fixture')=>{let reply;listener({type},{id:sender},value=>reply=value);return reply;},clicks:()=>clicks};
}
test('upload errors need not be the final line or unformatted',()=>{
  const f=fixture({text:'**SC_UPLOAD_BLOCKED: PSD_MAPPING**\nThe saved artwork is retained.'});
  assert.equal(f.send('project:progress').blocked,true);
  assert.match(f.send('project:progress').reason,/PSD_MAPPING/);
});
test('visible ChatGPT errors and unfinished generation are reported honestly',()=>{
  const f=fixture({alert:'Something went wrong. Please try again.'});
  assert.equal(f.send('project:progress').blocked,true);
  const busy=fixture({text:'Working on the upload',generating:true});
  assert.equal(busy.send('project:progress').finished,false);
  assert.equal(busy.send('project:cancel').stopped,true);
  assert.equal(busy.clicks(),1);
  assert.equal(busy.send('project:cancel','other-extension'),undefined);
  assert.equal(busy.clicks(),1);
});
test('finished response supplies stable activity without claiming verified publication',()=>{
  const f=fixture({text:'The upload needs a manual check.'});
  const result=f.send('project:progress');
  assert.equal(result.finished,true);
  assert.equal(result.blocked,false);
  assert.equal(result.activity,f.send('project:progress').activity);
  assert.equal(fixture({design:true,text:'SC_DESIGN_BLOCKED: Missing PSD access\nSaved the preview.'}).send('project:progress').blocked,true);
});
