const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const source = fs.readFileSync(process.env.SC_COMPOSER_TEST_SOURCE || path.join(__dirname, '../windows-upload-companion/composer.js'), 'utf8');
const project = 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project';
const conversation = 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b-sc-mockups-uploads/c/01234567-0123-0123-0123-0123456789ab';

function fixture({work = true, asAttachment = false, attachmentReadyAfter = 0, initialDraft = '',
  initialFiles = [], design = false, ad = false, start = 3, total = 6, canSet = true, powerAvailable = true,
  resetAfterPaste = false, draftBackupOK = true, ignoreEscape = false,
  replacePicker = false, menuReadyAfter = 0, ignoreOpenKey = false, powerLabel = 'Power',
  splitPreview = false, mismatchedPreview = false, sendTypeButton = false,
  afterThinkingDelay = 0, afterPermitDelay = 0, acknowledge = true, attachmentPreview = false,
  invalidateAfterReopen = false, headerAvailable = true, duplicateSend = false,
  permitOK = true, cancelAfter = Infinity, afterPasteText = "", extraAfterPaste = false, renameReferenceAfterPaste = false} = {}) {
  const location = {href:ad ? 'https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/project' : design ? 'https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project' : project};
  const files = [...initialFiles];
  const sent = [];
  const thinking = [];
  const backups = [], notes = [];
  let inserted = '', current = false, listener, permitted = 0;
  let now = 0;
  let selected = start, expanded = false;
  let opened = 0, disabledUntil = 0;
  const trigger = {
    get textContent() {return headerAvailable ? `GPT-6.2 Astra Power ${selected}` : '';},
    focus() {},
    click() {expanded = !expanded;},
    getAttribute: name => name === 'aria-controls' ? 'picker' : String(replacePicker && opened ? false : expanded),
    dispatchEvent(event) {if (event.key === 'Enter' && !(ignoreOpenKey && !expanded)) {expanded = !expanded;if (expanded) {
      opened++;
      if (opened >= 2 && invalidateAfterReopen) files.length = 0;
    }}},
  };
  const liveTrigger = () => replacePicker && opened ? {...trigger,
    getAttribute:name => name === 'aria-controls' ? 'picker' : String(expanded)} : trigger;
  const power = {
    focus() {},
    getAttribute: () => powerLabel,
    dispatchEvent(event) {
      if (event.key === 'Escape' && !ignoreEscape) {
        expanded = false;
        if (opened >= 2) disabledUntil = now + afterThinkingDelay;
      }
      if (canSet && event.key === 'ArrowRight') selected = Math.min(total, selected + 1);
      if (canSet && event.key === 'ArrowLeft') selected = Math.max(1, selected - 1);
    },
  };
  const menu = {matches: () => true, querySelectorAll: query => query === '[role="menuitem"]'
    ? (powerAvailable && now >= menuReadyAfter ? [power] : []) : [{textContent:`Some setting, ${selected} of ${total}.`}]};
  const button = {isConnected:true, get disabled() {return now < Math.max(attachmentReadyAfter, disabledUntil);}, getAttribute:() => null, click() {
    assert.equal(this.disabled,false,'Never click a disabled Send');
    sent.push(inserted);
    thinking.push({selected, expanded});
    current = true;
    if (acknowledge) location.href = ad ? conversation.replace('6a387a17627081918e1700ec2783a12b-sc-mockups-uploads', '6a6bd98cd6f081918788b544dcdecfc2-sports-cave-meta-ads') : design ? conversation.replace('6a387a17627081918e1700ec2783a12b-sc-mockups-uploads', '6a1e449948e881919c1e345006d63654-sports-cave-designs') : conversation;
  }};
  const staleSend = {...button,disabled:true,getClientRects:()=>[]};
  const querySelector = query => query.includes('Select ChatGPT model') ? liveTrigger() :
    (sendTypeButton && !query.includes('button[aria-label="Send"]') ? null : duplicateSend ? staleSend : button);
  const previewButton = {getAttribute:()=>null, get textContent(){return mismatchedPreview ? 'An unrelated prompt that must never be sent instead' : inserted.replace(/\s+/g,' ').slice(0,78)+'…';}};
  const all = query => query.includes('send-button') ? (duplicateSend ? [staleSend,button] : [button]) :
    query === 'input[type="file"]' ? [] : query === 'button' ? [previewButton] :
    attachmentPreview && files.length && query.includes('data-testid') ? [...files,previewButton] : files;
  const form = {querySelector, querySelectorAll:all};
  const replacementForm = {querySelector, querySelectorAll:all};
  let editor;

  const node = {innerText:initialDraft, closest:() => form, matches:() => work, focus() {
    document.activeElement = this;
  }, dispatchEvent(event) {
    if (event.clipboardData.image) {
      files.push({getAttribute:()=> renameReferenceAfterPaste && inserted ? 'Remove original(5).webp' : 'Remove original.webp', parentElement:{textContent:''}});
      return;
    }
    inserted = event.clipboardData.getData('text/plain');
    if (resetAfterPaste) selected = 1;
    if (asAttachment) {
      files.push({getAttribute:() => 'Remove pasted text attachment', parentElement:{
        querySelector:() => splitPreview ? null : ({getAttribute:() => inserted.replace(/\s+/g, ' ').slice(0, 78) + '…'}),
      }});
      editor = {...node, innerText:afterPasteText, closest:() => replacementForm};
      if(extraAfterPaste)files.push({getAttribute:()=>"Remove unrelated.webp"});
    }
    else this.innerText = inserted;
  }};
  if (initialFiles.length) form.querySelectorAll = () => initialFiles;
  editor = node;
  const body = {get innerText() {return asAttachment ? '' : inserted;}, querySelector:() => asAttachment ? {} : null};
  const document = {
    body:{append:note=>notes.push(note)},
    createElement:()=>({style:{},children:[],append(...items){this.children.push(...items);}}),
    createRange:()=>({selectNodeContents(){}}),
    activeElement:null,
    getElementById: () => expanded ? menu : null,
    querySelector(query) {
      if (query.includes('stop-button'))return null;
      if (query.includes('data-message-author-role'))return current ? {} : null;
      if (query.startsWith('[role='))return work ? editor : null;
      return work ? null : node;
    },
    querySelectorAll(query) {
      if (query.includes('Select ChatGPT model')) return [liveTrigger()];
      if (!current)return [];
      if (query.startsWith('h4'))return work ? [{nextElementSibling:body}] : [];
      return work ? [] : [{querySelector:() => body}];
    },
    execCommand(_name, _showUI, value) {inserted = value; node.innerText = value; return true;},
  };
  const chrome = {runtime:{id:'companion',onMessage:{addListener:callback => {listener=callback;}},sendMessage:async message => {
    if(message.type==='project:backup-draft') {if(draftBackupOK)backups.push(message.text);return {ok:draftBackupOK};}
    permitted++;
    disabledUntil = now + afterPermitDelay;
    return {ok:permitOK};
  }}};
  class Transfer {
    items = {add:() => {this.image=true;}};
    setData(_type, value) {this.value = value;}
    getData() {return this.value;}
  }
  class Paste {
    constructor(_type, options) {this.clipboardData = options.clipboardData;}
  }
  vm.runInNewContext(source, {location, document, chrome, window:{getSelection:()=>({removeAllRanges(){},addRange(){}})}, DataTransfer:Transfer, ClipboardEvent:Paste,
    File:class {}, atob, crypto:require('node:crypto').webcrypto,
    KeyboardEvent:class {constructor(_type, options) {this.key = options.key;}},
    Date:{now:() => now}, setTimeout(callback, ms) {now += ms;
      if(now>=cancelAfter)listener({type:'project:cancel'},{id:'companion'},()=>{});
      queueMicrotask(callback);},
  });
  function invoke(message) {
    return new Promise(resolve => listener(message,{id:'companion'},resolve));
  }
  return {invoke, sent, thinking, backups, notes, draft:()=>node.innerText, inserted:() => inserted,
    permitted:() => permitted, menuOpens:()=>opened};
}

test('Work waits for the delayed upload, submits the full pasted-text attachment and confirms its user turn', async () => {
  const browser = fixture({asAttachment:true, attachmentReadyAfter:9000});
  const prompt = 'Run this Product Uploads workflow for Jahmyr Gibbs.\n' + 'Full workflow •\n'.repeat(10000);
  assert.equal((await browser.invoke({type:'project:ready'})).ready,true);
  assert.equal((await browser.invoke({type:'project:send',id:'receipt',prompt})).sent,true);
  assert.deepEqual(browser.sent,[prompt]);
  assert.deepEqual(browser.thinking,[{selected:5, expanded:false}]);
  assert.equal(browser.permitted(),1);
});

test('Image plus pasted prompt submits once with split preview, type=button Send and an Escape-resistant model menu', async () => {
  const bytes=Buffer.from('offline reference image');
  const reference={name:'original.webp',type:'image/webp',size:bytes.length,data:bytes.toString('base64'),
    sha256:require('node:crypto').createHash('sha256').update(bytes).digest('hex')};
  const prompt='Run this Product Uploads workflow for Silver & Soul.\n'+'Complete workflow\n'.repeat(100);
  for (const config of [{}, {splitPreview:true}, {sendTypeButton:true}, {ignoreEscape:true},
    {splitPreview:true,sendTypeButton:true,ignoreEscape:true}]) {
    const app=fixture({asAttachment:true,...config});
    const result=await app.invoke({type:'project:send',id:'combined',prompt,reference});
    assert.equal(result.sent,true,JSON.stringify(config));
    assert.deepEqual(app.sent,[prompt]);
    assert.equal(app.permitted(),1);
    assert.deepEqual(app.thinking,[{selected:5,expanded:false}]);
  }
  // Preview labels may change independently of the exact pasted payload.
  const app=fixture({design:true,asAttachment:true,splitPreview:true,mismatchedPreview:true});
  assert.equal((await app.invoke({type:'project:send',id:'preview',prompt})).sent,true);
  assert.deepEqual(app.sent,[prompt]);
});

test('Uploads waits for enabled Send after both attachments, model adjustment and the send reservation, then clicks once', async () => {
  const bytes=Buffer.from('offline reference image');
  const reference={name:'original.webp',type:'image/webp',size:bytes.length,data:bytes.toString('base64'),
    sha256:require('node:crypto').createHash('sha256').update(bytes).digest('hex')};
  const prompt='Run this Product Uploads workflow for Silver & Soul.\n'+'Full exact prompt\n'.repeat(1000);
  for (const config of [
    {attachmentReadyAfter:45000},
    {afterThinkingDelay:10000},
    {afterPermitDelay:5000},
    {splitPreview:true,mismatchedPreview:true,attachmentPreview:true},
    {attachmentReadyAfter:45000,afterThinkingDelay:10000,afterPermitDelay:5000,total:8},
  ]) {
    const app=fixture({asAttachment:true,...config});
    const result=await app.invoke({type:'project:send',id:'wait-send',prompt,reference});
    assert.equal(result.sent,true,JSON.stringify(config));
    assert.deepEqual(app.sent,[prompt]);
    assert.equal(app.permitted(),1);
    assert.deepEqual(app.thinking,[{selected:(config.total||6)-1,expanded:false}]);
  }
  const unavailable=fixture({asAttachment:true,attachmentReadyAfter:Infinity});
  assert.equal((await unavailable.invoke({type:'project:send',id:'no-send',prompt,reference})).sent,false);
  assert.deepEqual(unavailable.sent,[]);
  assert.equal(unavailable.permitted(),0);
  const lostAck=fixture({asAttachment:true,acknowledge:false});
  assert.equal((await lostAck.invoke({type:'project:send',id:'lost-ack',prompt,reference})).sent,false);
  assert.deepEqual(lostAck.sent,[prompt],'Missing acknowledgement must not cause a second click');
  assert.equal(lostAck.permitted(),1);
});

test('Work and Chat submit intact inline text and leave existing drafts alone', async () => {
  for (const work of [true,false]) {
    const browser = fixture({work});
    const prompt = 'Complete prompt\n\nUse this exact content.';
    assert.equal((await browser.invoke({type:'project:send',id:'receipt',prompt})).sent,true);
    assert.deepEqual(browser.sent,[prompt]);
  }
  for (const initial of [{initialDraft:'Staff draft'}, {initialFiles:[{getAttribute:()=>'Remove pasted text attachment'}]}]) {
    const browser = fixture(initial);
    assert.equal((await browser.invoke({type:'project:send',id:'receipt',prompt:'New job'})).sent,false);
    assert.equal(browser.permitted(),0);
    assert.deepEqual(browser.sent,[]);
  }
});

test('A verified unchanged power setting never reopens the menu on the ready image/prompt draft', async () => {
  const bytes=Buffer.from('offline reference image');
  const reference={name:'original.webp',type:'image/webp',size:bytes.length,data:bytes.toString('base64'),
    sha256:require('node:crypto').createHash('sha256').update(bytes).digest('hex')};
  const prompt='Run this Product Uploads workflow for Silver & Soul.\n'+'Exact prompt\n'.repeat(100);
  for (const config of [{invalidateAfterReopen:true}, {duplicateSend:true}]) {
    const app=fixture({asAttachment:true,...config});
    assert.equal((await app.invoke({type:'project:send',id:'no-rerender',prompt,reference})).sent,true,JSON.stringify(config));
    assert.equal(app.menuOpens(),1);
    assert.deepEqual(app.sent,[prompt]);
    assert.deepEqual(app.thinking,[{selected:5,expanded:false}]);
  }
  for (const config of [{headerAvailable:false,invalidateAfterReopen:true}, {design:true,headerAvailable:false,invalidateAfterReopen:true}]) {
    const app=fixture({asAttachment:true,...config});
    assert.equal((await app.invoke({type:'project:send',id:'recheck-needed',prompt,reference})).sent,true);
    assert.equal(app.menuOpens(),1,'Do not disturb a ready draft to read the model again');
    assert.deepEqual(app.thinking,[{selected:5,expanded:false}]);
  }
});

test('Only a new Companion-owned upload tab backs up a restored draft and sends the exact upload prompt', async () => {
  const draft='My unfinished design instructions\nDo not send these.';
  const app=fixture({initialDraft:draft});
  const prompt='Run this Product Uploads workflow for Current product.\nExact upload content.';
  assert.equal((await app.invoke({type:'project:send',id:'receipt',prompt,freshUpload:true})).sent,true);
  assert.deepEqual(app.backups,[draft]);
  assert.equal(app.notes[0].children[1].textContent,draft);
  assert.deepEqual(app.sent,[prompt]);
  assert.equal(app.permitted(),1);
  const failed=fixture({initialDraft:draft,draftBackupOK:false});
  assert.equal((await failed.invoke({type:'project:send',id:'receipt',prompt,freshUpload:true})).sent,false);
  assert.equal(failed.draft(),draft);
  assert.deepEqual(failed.sent,[]);
});


test('Design queue backs up restored drafts without sending their content', async () => {
  const app=fixture({design:true,initialDraft:'Unsent user draft'});
  assert.equal((await app.invoke({type:'project:send',id:'design-job',prompt:'Exact queued refresh'})).sent,true);
  assert.deepEqual(app.backups,['Unsent user draft']);
  assert.deepEqual(app.sent,['Exact queued refresh']);
});

test('Designs uses the same second-from-top thinking level for inline and attached prompts', async () => {
  for (const asAttachment of [false, true]) {
    const app = fixture({design:true, asAttachment, start:6});
    const prompt = 'Create a complete collector artwork. '.repeat(100);
    const result = await app.invoke({type:'project:send', id:'design-job', prompt});
    assert.equal(result.sent, true);
    assert.deepEqual(app.sent, [prompt]);
    assert.deepEqual(app.thinking,[{selected:5, expanded:false}]);
    assert.equal(app.permitted(), 1);
  }
});

test('Design queue tolerates replaced pickers, slow menus and click-only menu opening', async () => {
  for (const config of [{replacePicker:true}, {menuReadyAfter:4000},
    {ignoreOpenKey:true}, {powerLabel:'Power 6'},
    {replacePicker:true, menuReadyAfter:4000, powerLabel:'Power 6'}]) {
    const browser = fixture({design:true, start:6, ...config});
    const prompt = 'Exact Oscar design prompt and receipt.';
    const result = await browser.invoke({type:'project:send', id:'oscar', prompt});
    assert.equal(result.sent,true,JSON.stringify(config));
    assert.deepEqual(browser.sent,[prompt]);
    assert.deepEqual(browser.thinking,[{selected:5,expanded:false}]);
    assert.equal(browser.permitted(),1);
  }
});

test('Reads the number of stops before preparing the composer', async () => {
  for (const [config, expected] of [
    [{design:true, total:8, start:3, asAttachment:true},7],
    [{total:4, start:4},3],
  ]) {
    const browser = fixture(config);
    const result = await browser.invoke({type:'project:send', id:'receipt', prompt:'Complete design or upload prompt.'});
    assert.equal(result.sent,true);
    assert.deepEqual(browser.thinking,[{selected:expected, expanded:false}]);
  }
});

test('An unavailable or unverified level leaves the composer untouched and never permits send', async () => {
  for (const config of [{canSet:false}, {powerAvailable:false}, {start:1, total:1}]) {
    const browser = fixture(config);
    const result = await browser.invoke({type:'project:send', id:'receipt', prompt:'A prompt'});
    assert.equal(result.sent,false);
    assert.match(result.reason,/Could not verify one step below maximum/);
    assert.equal(browser.inserted(),'');
    assert.equal(browser.permitted(),0);
  }
});


test('Both projects submit slow attachments despite abbreviated preview and missing model label', async () => {
  const prompt='Complete the supplied artwork workflow. '.repeat(1000);
  for (const design of [true,false]) {
    const app=fixture({design,asAttachment:true,attachmentReadyAfter:65000,
      headerAvailable:false,invalidateAfterReopen:true,mismatchedPreview:true,splitPreview:true});
    const result=await app.invoke({type:'project:send',id:'slow-project',prompt});
    assert.equal(result.sent,true,result.reason);
    assert.equal(app.menuOpens(),1);
    assert.equal(app.permitted(),1);
    assert.deepEqual(app.sent,[prompt]);
    assert.deepEqual(app.thinking,[{selected:5,expanded:false}]);
  }
});


test('Ready Send still refuses cancelled jobs, denied permits, extra attachments and edited drafts', async () => {
  for(const config of [{permitOK:false},{cancelAfter:150,attachmentReadyAfter:1000},
    {afterPasteText:'User changed this draft'},{extraAfterPaste:true}]) {
    const app=fixture({asAttachment:true,...config});
    const result=await app.invoke({type:'project:send',id:'guard',prompt:'Exact owned prompt. '.repeat(50)});
    assert.equal(result.sent,false,JSON.stringify(config));
    assert.deepEqual(app.sent,[]);
  }
});


test('Live regression: ChatGPT renames the verified reference after upload and Send still submits once', async () => {
  const bytes=Buffer.from('verified offline original');
  const reference={name:'original.webp',type:'image/webp',size:bytes.length,data:bytes.toString('base64'),
    sha256:require('node:crypto').createHash('sha256').update(bytes).digest('hex')};
  const app=fixture({asAttachment:true,renameReferenceAfterPaste:true});
  const prompt='Run this Product Uploads workflow for Silver & Soul. '.repeat(100);
  const result=await app.invoke({type:'project:send',id:'live-rename',prompt,reference});
  assert.equal(result.sent,true,result.reason);
  assert.deepEqual(app.sent,[prompt]);
  assert.equal(app.permitted(),1);
});
test('Meta Ads retains one-step-below-maximum submission without reopening the prepared composer', async () => {
  const browser = fixture({ad:true, asAttachment:true, total:7, invalidateAfterReopen:true});
  const prompt = 'Sports Cave automatic ad job\n' + 'Use the exact Dropbox image. '.repeat(200);
  assert.equal((await browser.invoke({type:'project:send', id:'ad', prompt})).sent,true);
  assert.deepEqual(browser.sent,[prompt]);
  assert.deepEqual(browser.thinking,[{selected:6, expanded:false}]);
  assert.equal(browser.permitted(),1);
});
