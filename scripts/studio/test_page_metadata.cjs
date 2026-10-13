const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const js=fs.readFileSync(__dirname+'/isolation/controller.py','utf8').match(/PAGE_METADATA=r'''([\s\S]*?)'''/)[1];
const catalog=[{key:'__signin__',route:'',label:'Sign in'},{key:'dashboard',route:'Dashboard',label:'Home'},{key:'orders',route:'Orders',label:'Orders'}];
const node=(text,kind='primary')=>({innerText:text,querySelector:()=>null,getAttribute:()=>kind,getBoundingClientRect:()=>({x:0,y:0,width:100,height:20,bottom:20})});
let root={dataset:{currentRouteKey:'orders',navigationEpoch:'3'}},login=null;
const document={getElementById:()=>root,querySelectorAll:()=>[node('Dashboard'),node('')],querySelector:()=>login};
const evaluate=vm.runInNewContext('('+js+')',{document,location:{href:'http://127.0.0.1:8501/'},URL,innerHeight:900,getComputedStyle:()=>({visibility:'visible'})});
assert.equal(evaluate(catalog).page,'orders');assert.equal(evaluate(catalog).epoch,3);assert.equal(evaluate(catalog).navigation.length,1);
root=null;assert.equal(evaluate(catalog).page,'dashboard');login={getClientRects:()=>[{}]};assert.equal(evaluate(catalog).page,'__signin__');console.log('Rendered route/epoch, collapsed sidebar, icon-only button and synthetic sign-in metadata passed');
