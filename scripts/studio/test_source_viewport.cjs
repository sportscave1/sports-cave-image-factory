const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(__dirname+'/ui/editor.js','utf8'),fn=source.slice(source.indexOf('function highlight()'),source.indexOf('function capture()'));
const original=Array.from({length:4000},(_,i)=>'const row'+i+' = "<script>safe</script>";').join('\n');
const nodes={'ed-source':{value:original,clientWidth:300,clientHeight:320,scrollTop:0,scrollLeft:0},'ed-wrap':{checked:false},'ed-lines':{},'ed-highlight':{}};
const ctx={$:id=>nodes[id],esc:s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),Math};vm.createContext(ctx);vm.runInContext(fn,ctx);ctx.highlight();
assert(nodes['ed-highlight'].innerHTML.length<12000);assert(!nodes['ed-highlight'].innerHTML.includes('<script>'));assert.equal(nodes['ed-source'].value,original);
nodes['ed-source'].scrollTop=20000;ctx.highlight();assert(nodes['ed-lines'].innerHTML.includes('1000'));assert(nodes['ed-highlight'].innerHTML.includes('row1000'));assert(nodes['ed-highlight'].innerHTML.length<12000);
nodes['ed-wrap'].checked=true;ctx.highlight();assert.equal(nodes['ed-source'].value,original);assert(nodes['ed-highlight'].innerHTML.length<12000);console.log('Bounded viewport syntax, line numbers, scrolling, wrapping and complete source preservation passed');
