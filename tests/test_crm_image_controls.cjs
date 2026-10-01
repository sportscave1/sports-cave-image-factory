const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('components/crm_sections/image.js','utf8');
const prompt=fs.readFileSync('prompts/sports_cave_email_image_v1.txt','utf8').trim();
class Node{
 constructor(tag){this.tag=tag;this.children=[];this.attrs={};this.style={};this.events={};this.open=false;}
 setAttribute(k,v){this.attrs[k]=v;} append(...nodes){this.children.push(...nodes);}
 addEventListener(k,fn){this.events[k]=fn;} matches(){return this.open;}
 hidePopover(){this.open=false;this.events.toggle?.();} showPopover(){this.open=true;this.events.toggle?.();}
 getBoundingClientRect(){return {bottom:50,right:300};} focus(options){this.focused=options;}
}
(async()=>{
 for(const fail of [false,true]){
  const timers=[],writes=[],row=new Node('div');
  const ctx=vm.createContext({document:{createElement:tag=>new Node(tag)},crypto:{randomUUID:()=> 'fixture'},innerWidth:500,innerHeight:700,
   window:{addEventListener(){},scCopyText:async text=>{if(fail)return false;writes.push(text);return true;}},setTimeout:(fn,ms)=>timers.push({fn,ms})});
  vm.runInContext(source,ctx);ctx.imageControls(row,prompt);
  const [copy,help,popup]=row.children;
  assert.equal(copy.type,'button');assert.equal(help.type,'button');assert.equal(popup.attrs.popover,'auto');
  help.onclick();assert.equal(popup.open,true);assert.equal(help.attrs['aria-expanded'],'true');
  row.events.keydown({key:'Escape',preventDefault(){}});assert.equal(popup.open,false);assert.equal(help.focused.preventScroll,true);
  await copy.onclick();
  if(fail){assert.equal(copy.textContent,'Copy prompt');const fallback=popup.children.at(-1);assert.equal(fallback.hidden,false);assert.equal(fallback.children[1].value,prompt);assert.equal(fallback.children[1].readOnly,true);}
  else{assert.deepEqual(writes,[prompt]);assert.equal(copy.textContent,'✓ Prompt copied');assert.equal(timers[0].ms,1800);timers[0].fn();assert.equal(copy.textContent,'Copy prompt');}
 }
 // Actual advice function with parsed-attribute fixtures; browser covers native DOMParser.
 const image=attrs=>({getAttribute:k=>attrs[k]??null,hasAttribute:k=>k in attrs,alt:attrs.alt||'',style:{width:'100%',maxWidth:'600px',height:'auto'}});
 let nodes=[image({src:'https://cdn.shopify.com/art.jpg',alt:'Artwork',width:'600'})];
 const ctx=vm.createContext({URL,DOMParser:class{parseFromString(){return {querySelectorAll:()=>nodes};}}});vm.runInContext(source,ctx);
 assert.match(ctx.imageAdvice('html'),/✓ HTTPS/);
 nodes=[image({src:'data:image/png;base64,AA',width:'600'})];assert.match(ctx.imageAdvice('html'),/Data\/base64/);assert.match(ctx.imageAdvice('html'),/Missing alt/);
 nodes=[image({src:'http://example.test/a.jpg',alt:'',width:'600'})];assert.match(ctx.imageAdvice('html'),/valid HTTPS/);assert.match(ctx.imageAdvice('html'),/meaningful/);
 nodes[0].style.width='900px';assert.match(ctx.imageAdvice('html'),/overflow/);
 console.log('Image clipboard success/denial, exact template, feedback expiry, help/Escape, and 6 validation checks passed');
})();
