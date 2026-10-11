const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('app.py','utf8'),start=source.indexOf('// Email recovery text is tab-local');
assert.ok(start>0);const js=source.slice(start,source.indexOf("window.parent.fetch('/api/os/auth/clear-cookie'",start)).replaceAll('{{','{').replaceAll('}}','}');
const values=new Map([['sc-email-draft-v2:actor:mail:draft','private synthetic text'],['other-app-preference','keep']]);
const storage={get length(){return values.size},key:i=>[...values.keys()][i],removeItem:k=>values.delete(k)};
vm.runInNewContext(js,{window:{parent:{sessionStorage:storage}}});
assert.deepEqual([...values.entries()],[['other-app-preference','keep']]);
vm.runInNewContext(js,{window:{get parent(){throw Error('Unavailable storage')}}});
console.log('Actual sign-in/sign-out script clears only Email journals; unavailable storage cannot break authentication.');
