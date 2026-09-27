// Execute the production shared badge helper against a small DOM-shaped fixture.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('components/sports_cave_top_bar/index.html','utf8');
const rows={};
for(const route of ['orders','email']) {
  const attrs={},button={dataset:{},badge:null,
    querySelector(){return this.badge;},
    appendChild(node){this.badge=node;node.remove=()=>this.badge=null;},
    setAttribute(key,value){attrs[key]=value;},
    removeAttribute(key){delete attrs[key];},attrs};
  rows[route]={querySelector(){return button;},button};
}
const context={doc:{querySelector(selector){return rows[selector.endsWith('-email')?'email':'orders'];},
  createElement(){return {setAttribute(){},textContent:''};}},later(){throw Error('unexpected retry');}};
vm.createContext(context);
const code=source.slice(source.indexOf('const updateSidebarBadge ='),source.indexOf('const applyEmailStatus ='));
vm.runInContext(code+';this.badge=updateSidebarBadge;this.orders=updateOrdersBadge;',context);
context.orders(7,'7');
let assertions=0;
for(const count of [0,1,3,99,100,0]) {
  context.badge('email',count,'');
  const badge=rows.email.button.badge;
  assert.equal(Boolean(badge),count>0);assertions++;
  if(count){
    assert.equal(badge.className,rows.orders.button.badge.className);assertions++;
    assert.equal(badge.textContent,count>99?'99+':String(count));assertions++;
    assert.equal(rows.email.button.attrs['aria-label'],`Email, ${count} unread`);assertions++;
  }
}
assert.equal(rows.orders.button.badge.textContent,'7');assertions++;
assert.equal(rows.email.button.attrs['aria-label'],'Email');assertions++;
assert.match(source,/later\(refreshOrderStatus, ORDER_STATUS_REFRESH_MS\)/);assertions++;
assert.doesNotMatch(source,/setInterval\(refreshEmailStatus|later\(refreshEmailStatus/);assertions++;
console.log(`Shared notification badge checks passed (${assertions} assertions).`);
