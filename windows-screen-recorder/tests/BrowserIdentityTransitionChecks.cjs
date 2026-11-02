const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
class Element {
  constructor(tag='SPAN',id='') { this.tagName=tag;this.id=id;this.attrs={};this.style={};this.dataset={};this.textContent=''; }
  matches(s){return this.tagName==='DIV'&&this.attrs.contenteditable==='true'&&this.attrs.role==='textbox';}
  getAttribute(k){return this.attrs[k]??null;}
  setAttribute(k,v){this.attrs[k]=v;}
}
const marker=new Element('SPAN','sc-recorder-document');
const button=new Element('BUTTON','nav-home');button.textContent='Home';
let contexts=[{dataset:{ready:'true',productSha256:'a'.repeat(64)}}], controls=[button], tick;
const doc={body:{append(){}},addEventListener(){},getElementById(id){return id===marker.id?marker:null;},
 querySelectorAll(s){return s==='#sc-recorder-context'?contexts:controls;}};
const host={document:doc,location:new URL('http://127.0.0.1:18963/?page=product_uploads'),
 localStorage:{getItem(){return '56578ebe-3793-47ba-b81f-fbc2c2755cf9';}},addEventListener(){}};
const sandbox={SportsCavePreparedContext:{read:n=>n.dataset.ready==='true'?n.dataset.productSha256:null},window:host,top:host,document:doc,URL,URLSearchParams,crypto:{randomUUID:()=> 'test-document'},
 MutationObserver:class{observe(){}},queueMicrotask:f=>f(),setInterval:f=>{tick=f;}};
vm.runInNewContext(fs.readFileSync(process.argv[2]||__dirname+'/../edge-adapter/browser-identity.js','utf8'),sandbox);
const identity=e=>{const s=(e.getAttribute('title')||'').split('\n').find(x=>x.startsWith('Sports Cave browser v2: '));return s?JSON.parse(decodeURIComponent(s.slice(24))):null;};
assert.equal(identity(marker).product,'a'.repeat(64));
// Pending or malformed fingerprints must never downgrade a ready product scope.
contexts=[{dataset:{ready:'true'}}];tick();
assert.equal(identity(marker),null);assert.equal(identity(button),null);
contexts=[{dataset:{ready:'true',productSha256:'a'.repeat(64)}}];tick();
assert.equal(identity(marker).product,'a'.repeat(64));
contexts.push(contexts[0]);tick();assert.equal(identity(marker),null);
contexts.pop();tick();assert.equal(identity(marker).product,'a'.repeat(64));
// The exact failed trace: URL changes while the previous context remains.
host.location=new URL('http://127.0.0.1:18963/?page=dashboard');tick();
assert.equal(identity(marker),null);assert.equal(identity(button),null);
contexts=[];tick();assert.equal(identity(marker).page,host.location.href);assert.equal(identity(marker).product,undefined);
host.location=new URL('http://127.0.0.1:18963/?page=product_uploads');
contexts=[{dataset:{ready:'true',productSha256:'b'.repeat(64)}}];tick();
assert.equal(identity(marker).product,'b'.repeat(64));assert.equal(identity(button).product,'b'.repeat(64));
// Existing unique-control guard still removes ambiguous identities.
const duplicate=new Element('BUTTON','nav-home');duplicate.textContent='Home';controls.push(duplicate);tick();
assert.equal(identity(button),null);assert.equal(identity(duplicate),null);
console.log('PASS: mixed-page identity withheld; settled pages and product changes retained; ambiguous controls rejected');

host.location=new URL('https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project');contexts=[];
const composer=new Element('DIV');composer.setAttribute('contenteditable','true');composer.setAttribute('role','textbox');
composer.setAttribute('aria-label','New chat in SC Mockups/Uploads');controls=[composer];tick();
assert.ok(composer.getAttribute('title').includes('Sports Cave composer v1: empty'));
composer.textContent='Private test text not to be exported';tick();
assert.ok(composer.getAttribute('title').includes('Sports Cave composer v1: nonempty'));
assert.ok(!composer.getAttribute('title').includes(composer.textContent));
composer.textContent=' ';tick();assert.ok(composer.getAttribute('title').includes('Sports Cave composer v1: nonempty'));
host.location=new URL('https://chatgpt.com/c/unrelated');tick();
assert.ok(!composer.getAttribute('title').includes('Sports Cave composer v1:'));
console.log('PASS: exact project empty/nonempty composer marker; whitespace retained; no field text exported');
