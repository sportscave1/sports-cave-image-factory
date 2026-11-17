const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../windows-upload-companion/composer.js'), 'utf8');
const project = 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project';
const conversation = 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b-sc-mockups-uploads/c/01234567-0123-0123-0123-0123456789ab';

function fixture({work = true, asAttachment = false, attachmentReadyAfter = 0, initialDraft = '',
  initialFiles = [], design = false, start = 3, total = 6, canSet = true, powerAvailable = true,
  resetAfterPaste = false, draftBackupOK = true} = {}) {
  const location = {href:design ? 'https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project' : project};
  const files = [...initialFiles];
  const sent = [];
  const thinking = [];
  const backups = [], notes = [];
  let inserted = '', current = false, listener, permitted = 0;
  let now = 0;
  let selected = start, expanded = false;
  const trigger = {
    focus() {},
    getAttribute: name => name === 'aria-controls' ? 'picker' : String(expanded),
    dispatchEvent(event) {if (event.key === 'Enter') expanded = !expanded;},
  };
  const power = {
    focus() {},
    getAttribute: () => 'Power',
    dispatchEvent(event) {
      if (event.key === 'Escape') expanded = false;
      if (canSet && event.key === 'ArrowRight') selected = Math.min(total, selected + 1);
      if (canSet && event.key === 'ArrowLeft') selected = Math.max(1, selected - 1);
    },
  };
  const menu = {matches: () => true, querySelectorAll: query => query === '[role="menuitem"]'
    ? (powerAvailable ? [power] : []) : [{textContent:`Some setting, ${selected} of ${total}.`}]};
  const button = {isConnected:true, get disabled() {return now < attachmentReadyAfter;}, getAttribute:() => null, click() {
    sent.push(inserted);
    thinking.push({selected, expanded});
    current = true;
    location.href = design ? conversation.replace('6a387a17627081918e1700ec2783a12b-sc-mockups-uploads', '6a1e449948e881919c1e345006d63654-sports-cave-designs') : conversation;
  }};
  const querySelector = query => query.includes('Select ChatGPT model') ? trigger : button;
  const form = {querySelector, querySelectorAll:() => []};
  const replacementForm = {querySelector, querySelectorAll:() => files};
  let editor;

  const node = {innerText:initialDraft, closest:() => form, matches:() => work, focus() {
    document.activeElement = this;
  }, dispatchEvent(event) {
    inserted = event.clipboardData.getData('text/plain');
    if (resetAfterPaste) selected = 1;
    if (asAttachment) {
      files.push({getAttribute:() => 'Remove pasted text attachment', parentElement:{
        querySelector:() => ({getAttribute:() => inserted.replace(/\s+/g, ' ').slice(0, 78) + '…'}),
      }});
      editor = {...node, closest:() => replacementForm};
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
      if (query.includes('data-message-author-role'))return current ? {} : null;
      if (query.startsWith('[role='))return work ? editor : null;
      return work ? null : node;
    },
    querySelectorAll(query) {
      if (query.includes('Select ChatGPT model')) return [trigger];
      if (!current)return [];
      if (query.startsWith('h4'))return work ? [{nextElementSibling:body}] : [];
      return work ? [] : [{querySelector:() => body}];
    },
    execCommand(_name, _showUI, value) {inserted = value; node.innerText = value; return true;},
  };
  const chrome = {runtime:{id:'companion',onMessage:{addListener:callback => {listener=callback;}},sendMessage:async message => {
    if(message.type==='project:backup-draft') {if(draftBackupOK)backups.push(message.text);return {ok:draftBackupOK};}
    permitted++;
    return {ok:true};
  }}};
  class Transfer {
    setData(_type, value) {this.value = value;}
    getData() {return this.value;}
  }
  class Paste {
    constructor(_type, options) {this.clipboardData = options.clipboardData;}
  }
  vm.runInNewContext(source, {location, document, chrome, window:{getSelection:()=>({removeAllRanges(){},addRange(){}})}, DataTransfer:Transfer, ClipboardEvent:Paste,
    KeyboardEvent:class {constructor(_type, options) {this.key = options.key;}},
    Date:{now:() => now}, setTimeout(callback, ms) {now += ms; queueMicrotask(callback);},
  });
  function invoke(message) {
    return new Promise(resolve => listener(message,{id:'companion'},resolve));
  }
  return {invoke, sent, thinking, backups, notes, draft:()=>node.innerText, inserted:() => inserted, permitted:() => permitted};
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

test('Reads the number of stops from the picker and rechecks after a composer replacement', async () => {
  for (const [config, expected] of [
    [{design:true, total:8, start:3, resetAfterPaste:true, asAttachment:true},7],
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
