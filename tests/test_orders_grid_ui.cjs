const test=require('node:test'),assert=require('node:assert/strict');
const core=require('../components/orders_prodigi_grid/grid-core.js');
const rows=Array.from({length:103},(_,i)=>({id:'allocation:'+i,cells:{prodigi:i%2?'Complete':'Needs certificate'},state:{tone:i===2?'success':''}}));

test('customer review holds stay actionable but are not labelled as failed orders',()=>{
 const held={review:{status:'Customer hold',customer_hold:true,has_error:false,can_restart:false},state:{tone:'warning'}};
 assert.equal(core.fulfilmentLabel(held),'Customer hold');
 assert.equal(core.category(held),'attention');
 const failed={review:{status:'Needs QA',customer_hold:true,has_error:true,can_restart:false}};
 assert.equal(core.fulfilmentLabel(failed),'× Needs attention');
 assert.equal(core.category(failed),'attention');
});

test('existing supplier production and queue labels remain independent of customer review',()=>{
 assert.equal(core.fulfilmentLabel({review:{status:'Complete',supplier_status:'in_production'}}),'In production');
 assert.equal(core.fulfilmentLabel({review:{status:'Submitted',supplier_status:'on_hold'}}),'On hold');
 assert.equal(core.fulfilmentLabel({review:{status:'Ready for manual payment',submission_enabled:true}}),'Submitting');
});
test('fifty-row pages preserve every unit including the last partial page',()=>{
 const pages=[0,1,2].map(p=>core.pageRows(rows,p));assert.deepEqual(pages.map(p=>p.length),[50,50,3]);
 assert.deepEqual(pages.flat().map(r=>r.id),rows.map(r=>r.id));assert.equal(core.PAGE_SIZE,50);
});
test('page selection preserves other-page identities and does not change the rows',()=>{
 const selected=new Set(['allocation:100']);const next=core.togglePage(selected,core.pageRows(rows,0),true);
 assert.equal(next.size,51);assert(next.has('allocation:100'));assert.equal(selected.size,1);
 const cleared=core.togglePage(next,core.pageRows(rows,0),false);assert.deepEqual([...cleared],['allocation:100']);
});
test('ready filter requires saved QA success rather than a missing-certificate label',()=>{
 assert.deepEqual(core.filtered(rows,'ready').map(r=>r.id),['allocation:2']);
 assert(core.filtered(rows,'attention').every(r=>r.cells.prodigi==='Needs certificate'&&r.state.tone!=='success'));
 assert(core.filtered(rows,'complete').every(r=>r.cells.prodigi==='Complete'));
 assert.equal(core.filtered(rows,'all').length,103);
});

test('countdown stays Submitted and completion follows the worker rather than stale certificate data',()=>{
 assert.equal(core.category({cells:{prodigi:'Complete'},review:{status:'Submitted'},state:{tone:'success'}}),'ready');
 assert.equal(core.category({cells:{prodigi:'Needs certificate'},review:{status:'Complete'},state:{tone:'success'}}),'complete');
 assert.equal(core.category({cells:{prodigi:'Needs certificate'},review:{status:'Queued',can_restart:false},state:{tone:'pending'}}),'progress');
});

test('items from the same supplier order stay together without grouping a customer name alone',()=>{
 const a={id:'a',cells:{order:'#1',customer:'Same name'},review:{order_url:'https://dashboard.prodigi.com/orders/1/detail'}};
 const b={id:'b',cells:{order:'#2',customer:'Same name'},review:{order_url:'https://dashboard.prodigi.com/orders/2/detail'}};
 const c={id:'c',cells:{order:'#1',customer:'Same name'},review:{order_url:a.review.order_url}};
 assert.deepEqual(core.orderGroups([a,b,c]).map(r=>r.id),['a','c','b']);
 assert.deepEqual(core.siblings([a,b,c],a).map(r=>r.id),['a','c']);
 assert.deepEqual(core.siblings([a,b,c],b).map(r=>r.id),['b']);
 assert.deepEqual(core.orderGroups([a,b,c]),[a,c,b]);
});
