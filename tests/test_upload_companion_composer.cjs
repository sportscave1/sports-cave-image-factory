const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../windows-upload-companion/composer.js'), 'utf8');
const project = 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project';
const conversation = 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b-sc-mockups-uploads/c/01234567-0123-0123-0123-0123456789ab';

function fixture({work = true, asAttachment = false, attachmentReadyAfter = 0, initialDraft = '', initialFiles = [], design = false} = {}) {
  const location = {href:design ? 'https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project' : project};
  const files = [...initialFiles];
  const sent = [];
  let inserted = '', current = false, listener, permitted = 0;
  let now = 0;
  const button = {isConnected:true, get disabled() {return now < attachmentReadyAfter;}, getAttribute:() => null, click() {
    sent.push(inserted);
    current = true;
    location.href = design ? conversation.replace('6a387a17627081918e1700ec2783a12b-sc-mockups-uploads', '6a1e449948e881919c1e345006d63654-sports-cave-designs') : conversation;
  }};
  const form = {querySelector:() => button, querySelectorAll:() => []};
  const replacementForm = {querySelector:() => button, querySelectorAll:() => files};
  let editor;

  const node = {innerText:initialDraft, closest:() => form, matches:() => work, focus() {
    document.activeElement = this;
  }, dispatchEvent(event) {
    inserted = event.clipboardData.getData('text/plain');
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
    activeElement:null,
    querySelector(query) {
      if (query.includes('data-message-author-role'))return current ? {} : null;
      if (query.startsWith('[role='))return work ? editor : null;
      return work ? null : node;
    },
    querySelectorAll(query) {
      if (!current)return [];
      if (query.startsWith('h4'))return work ? [{nextElementSibling:body}] : [];
      return work ? [] : [{querySelector:() => body}];
    },
    execCommand(_name, _showUI, value) {inserted = value; node.innerText = value; return true;},
  };
  const chrome = {runtime:{id:'companion',onMessage:{addListener:callback => {listener=callback;}},sendMessage:async () => {
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
  vm.runInNewContext(source, {location, document, chrome, DataTransfer:Transfer, ClipboardEvent:Paste,
    Date:{now:() => now}, setTimeout(callback, ms) {now += ms; queueMicrotask(callback);},
  });
  function invoke(message) {
    return new Promise(resolve => listener(message,{id:'companion'},resolve));
  }
  return {invoke, sent, permitted:() => permitted};
}

test('Work waits for the delayed upload, submits the full pasted-text attachment and confirms its user turn', async () => {
  const browser = fixture({asAttachment:true, attachmentReadyAfter:9000});
  const prompt = 'Run this Product Uploads workflow for Jahmyr Gibbs.\n' + 'Full workflow •\n'.repeat(10000);
  assert.equal((await browser.invoke({type:'project:ready'})).ready,true);
  assert.equal((await browser.invoke({type:'project:send',id:'receipt',prompt})).sent,true);
  assert.deepEqual(browser.sent,[prompt]);
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


test('Design project uses the same verified paste and submit flow for inline and attached prompts', async () => {
  for (const asAttachment of [false, true]) {
    const app = fixture({design:true, asAttachment});
    const prompt = 'Create a complete collector artwork. '.repeat(100);
    const result = await app.invoke({type:'project:send', id:'design-job', prompt});
    assert.equal(result.sent, true);
    assert.deepEqual(app.sent, [prompt]);
    assert.equal(app.permitted(), 1);
  }
});
