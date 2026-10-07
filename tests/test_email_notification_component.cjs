// Execute the production shared badge helper against a small DOM-shaped fixture.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('components/sports_cave_top_bar/index.html','utf8');
const rows={};
for(const route of ['orders','emailClosed','emailOpen','inbox']) {
  const attrs={},button={dataset:{},badge:null,
    querySelector(){return this.badge;},
    appendChild(node){this.badge=node;node.remove=()=>this.badge=null;},
    setAttribute(key,value){attrs[key]=value;},
    removeAttribute(key){delete attrs[key];},attrs};
  rows[route]={querySelector(){return button;},button};
}
let expanded=false;
const context={doc:{querySelector(selector){
  if(selector==='section[data-testid="stSidebar"] [class*="st-key-sidebar-disclosure-email-"]')
    return rows[expanded?'emailOpen':'emailClosed'];
  if(selector==='section[data-testid="stSidebar"] .st-key-sidebar-row-email button')
    return expanded?rows.inbox.button:null;
  assert.equal(selector,'section[data-testid="stSidebar"] .st-key-sidebar-row-orders');
  return rows.orders;
},createElement(){return {setAttribute(){},textContent:''};}},later(){throw Error('unexpected retry');}};
vm.createContext(context);
const code=source.slice(source.indexOf('const updateSidebarBadge ='),source.indexOf('const applyEmailStatus ='));
vm.runInContext(code+';this.badge=updateSidebarBadge;this.orders=updateOrdersBadge;',context);
context.orders(7,'7');
for(const isExpanded of [false,true]) {
  expanded=isExpanded;
  const parent=rows[expanded?'emailOpen':'emailClosed'].button;
  for(const count of [0,1,3,99,100,0]) {
    context.badge('email',count,'');
    assert.equal(Boolean(parent.badge),count>0);
    assert.equal(rows.inbox.button.badge,null);
    if(count){
      assert.equal(parent.badge.className,rows.orders.button.badge.className);
      assert.equal(parent.badge.textContent,count>99?'99+':String(count));
      assert.equal(parent.attrs['aria-label'],`Email, ${count} unread`);
    }
  }
  assert.equal(parent.attrs['aria-label'],'Email');
}
// Expanding keeps the count on the parent and clears any stale child badge.
expanded=false;
context.badge('email',1,'');
assert.equal(rows.emailClosed.button.badge.textContent,'1');
expanded=true;
rows.inbox.button.appendChild({});
rows.inbox.button.setAttribute('data-action-required-count','1');
rows.inbox.button.setAttribute('aria-label','Email, 1 unread');
context.badge('email',1,'');
assert.equal(rows.emailOpen.button.badge.textContent,'1');
assert.equal(rows.inbox.button.badge,null);
assert.equal(rows.inbox.button.attrs['data-action-required-count'],undefined);
assert.equal(rows.inbox.button.attrs['aria-label'],undefined);
// The existing unread update clears the parent after reading messages.
context.badge('email',0,'');
assert.equal(rows.emailOpen.button.badge,null);
assert.equal(rows.orders.button.badge.textContent,'7');
assert.match(source,/updateSidebarBadge\("email", payload.unread_count, ""\)/);
assert.match(source,/button span.sc-orders-action-badge \{[^}]*pointer-events: none;/);
assert.match(source,/\[class\*="st-key-sidebar-disclosure-email-"\] button span.sc-orders-action-badge \{\s*right: 34px;/);
assert.match(source,/state.config.emailEnabled \|\| state.config.wallInboxEnabled/);
assert.doesNotMatch(source,/setInterval\(refreshEmailStatus|later\(refreshEmailStatus/);
console.log('Shared notification badge checks passed (collapsed/expanded, zero/unread, clear, no duplicate, Orders unchanged).');
