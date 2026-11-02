// Offline execution of the real adapter script. No browser or user input.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../edge-adapter/browser-identity.js'),'utf8');
function run({trusted=true,duplicate=false,label='Save disposable file as',origin='http://127.0.0.1:18963',screenX=100,pageOnly=false,inspect=false}={}) {
  const elements=new Map(),listeners={},controls=[];
  function element(tag='SPAN') {
    const attrs={};const e={tagName:tag,id:'',name:'',textContent:'',style:{},dataset:{},
      getAttribute:k=>attrs[k]??null,hasAttribute:k=>k in attrs,setAttribute:(k,v)=>{attrs[k]=String(v);},
      matches:()=>true,closest:()=>e};
    Object.defineProperty(e,'title',{get:()=>attrs.title||'',set:v=>attrs.title=v});return e;
  }
  const link=element('A');link.id='save-as';link.textContent=label;link.href=origin+'/sample.txt';link.dataset.scSaveAs='true';link.setAttribute('download','sample.txt');controls.push(link);
  if(duplicate)controls.push({...link});
  const doc={addEventListener:(k,f)=>listeners[k]=f,getElementById:id=>elements.get(id),createElement:()=>element(),
    querySelectorAll:s=>s==='#sc-recorder-context'?[]:controls,body:{append:e=>elements.set(e.id,e)}};
  const host={document:doc,location:new URL(origin+'/recorder-acceptance/tab-a'),screenX,screenY:200,outerWidth:500,outerHeight:600,devicePixelRatio:1.4,
    localStorage:{getItem:()=> '56578ebe-3793-47ba-b81f-fbc2c2755cf9',setItem(){}},addEventListener(){}};
  let prevented=false,sent=0;
  vm.runInNewContext(source,{chrome:{runtime:{getManifest:()=>({permissions:pageOnly?[]:['downloads','nativeMessaging']}),sendMessage:()=>sent++}},window:host,top:host,document:doc,URL,URLSearchParams,crypto:{randomUUID:()=> '49c3a012-8dfc-426f-8f35-7b2aca074aff'},
    MutationObserver:class {observe(){}},setInterval(){},queueMicrotask(){},location:host.location});
  listeners.pointerdown?.({isTrusted:trusted,button:0,isPrimary:true,target:link,screenX:screenX+100,screenY:300});
  const title=elements.get('sc-recorder-button-gesture')?.title;
  listeners.click?.({isTrusted:trusted,target:link,preventDefault:()=>{prevented=true;}});
  const witness=title?JSON.parse(decodeURIComponent(title.slice('Sports Cave button gesture v2: '.length))):null;
  return inspect?{witness,url:link.href,prevented,sent}:witness;
}
let w=run();assert.equal(w.download.filename,'sample.txt');assert.equal(w.download.save_as,true);
assert.equal(w.pointer.x,140);assert.equal(w.pointer.y,140);assert.equal(w.pointer.scale,1.4);
assert.ok(w.download.url.includes('sc_download=49c3a012-8dfc-426f-8f35-7b2aca074aff'));
assert.equal(run({trusted:false}),null);assert.equal(run({duplicate:true}),null);assert.equal(run({label:'Password'}),null);
assert.equal(run({origin:'https://unapproved.example'}),null);
assert.equal(run({screenX:-1000}).pointer.x,140);
assert.equal(run({origin:'https://chatgpt.com'}).download,undefined);
const page=run({pageOnly:true,inspect:true});
assert.equal(page.witness.download,undefined);assert.equal(page.witness.pointer,undefined);
assert.equal(page.url,'http://127.0.0.1:18963/sample.txt');assert.equal(page.prevented,false);assert.equal(page.sent,0);
assert.ok(page.witness.identity);
const full=run({inspect:true});assert.equal(full.prevented,true);assert.equal(full.sent,1);
console.log('PASS 20 adapter witness and page-only download isolation checks; no browser acceptance claimed.');
