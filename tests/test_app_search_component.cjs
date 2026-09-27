const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {execFileSync}=require('node:child_process');
const {performance}=require('node:perf_hooks');
const source=fs.readFileSync('components/sports_cave_top_bar/index.html','utf8').replace(/\r\n/g,'\n');
const rows=JSON.parse(execFileSync('.venv/Scripts/python.exe',['-c',
  'import json, app_search, os_accounts; print(json.dumps(app_search.build_app_index([p["route"] for p in os_accounts.PAGE_REGISTRY],can_view_activity=True)))'],{encoding:'utf8'}));
const ctx={};vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('const normalise ='),source.indexOf('const renderSearchResults ='))+
  ';this.prepare=prepareSearchIndex;this.rank=rankSearchResults;',ctx);
const index=ctx.prepare(rows);
const titles=q=>Array.from(ctx.rank(index,q),r=>r.title);
for(const query of ['', '   ', ' - '])assert.deepEqual(titles(query),[]);
for(const [q,title] of [['email','Email'],['creative refresh','Creative Refresh'],['analtyics','Analytics'],
 ['fulfillment','Fulfilment'],['ga4','Analytics'],['inbox','Email'],['signature','Signatures'],['gsc','SEO'],
 ['  CREATIVE--  Refresh  ','Creative Refresh'],['product upload','Product Uploads']]) assert.equal(titles(q)[0],title,q);
for(const row of rows) assert.equal(titles(row.title)[0],row.title);
assert.ok(titles('email').includes('Email Settings'));
assert.ok(titles('email').includes('Customer Support'));
assert.ok(titles('meta').includes('Meta Review'));
assert.ok(titles('xyzxyzxyz').length===0);
assert.ok(titles('a').length<=8);
assert.deepEqual(titles('meta'),titles('META'));
const tiers=ctx.prepare([
 {title:'X emial'}, {title:'Other',aliases:['email']}, {title:'Email settings'},
 {title:'My email'}, {title:'Email'}, {title:'Alias prefix',aliases:['email inbox']},
 {title:'Keyword',keywords:['email']}, {title:'Emial'},
]);
assert.deepEqual(Array.from(ctx.rank(tiers,'email'),r=>r.title),['Email','Other','Email settings','Alias prefix','My email','Keyword','Emial']);

// Execute real rendering and outside/blur listeners with DOM-shaped boundaries.
let expanded=false,navigation='';const listeners={},windowListeners={};
const input={value:'',focus(){},contains:t=>t===input};
const panel={hidden:true,innerHTML:'',contains:t=>t===panel,querySelectorAll:()=>[]};
Object.assign(ctx,{state:{activePanel:'search',searchIndex:index}, searchInput:input,searchPanel:panel,
  setExpanded:(_,value)=>expanded=value,escapeHtml:s=>s.replaceAll('<','&lt;'),icon:()=>'',
  navigate:()=>{},updateHighlight:()=>{},root:{contains:()=>true},listenerOptions:{},
  doc:{addEventListener:(key,fn)=>listeners[key]=fn},
  parentWindow:{addEventListener:(key,fn)=>windowListeners[key]=fn},
  closePanels(){ctx.state.activePanel='';panel.hidden=true;},
  navigateDocument:url=>navigation=url,routeUrl:key=>key});
vm.runInContext(source.slice(source.indexOf('const renderSearchResults ='),source.indexOf('const updateHighlight ='))+';this.render=renderSearchResults;',ctx);
ctx.render();assert.equal(panel.hidden,true);assert.equal(panel.innerHTML,'');assert.equal(expanded,false);
input.value='email';ctx.render();assert.equal(panel.hidden,false);assert.equal(expanded,true);
assert.ok(!panel.innerHTML.includes('sc-os-result-group'));
vm.runInContext(source.slice(source.indexOf('doc.addEventListener("pointerdown"'),source.indexOf('doc.addEventListener("click", (event) => {\n      const seoViewButton')),ctx);
listeners.pointerdown({target:input});assert.equal(ctx.state.activePanel,'search');
listeners.pointerdown({target:panel});assert.equal(ctx.state.activePanel,'search');
listeners.pointerdown({target:{}});assert.equal(ctx.state.activePanel,'');
ctx.state.activePanel='search';windowListeners.blur();assert.equal(ctx.state.activePanel,'');
vm.runInContext(source.slice(source.indexOf('const navigate ='),source.indexOf('const setExpanded ='))+';this.go=navigate;',ctx);
ctx.go({route_key:'email',group:'Pages'});assert.equal(navigation,'email');assert.equal(input.value,'');assert.equal(panel.hidden,true);
const inputHandlers={};input.addEventListener=(key,handler)=>inputHandlers[key]=handler;
vm.runInContext(source.slice(source.indexOf('searchInput.addEventListener("input"'),source.indexOf('notificationsButton.addEventListener')),ctx);
ctx.state.activePanel='search';input.value='email';inputHandlers.input();
const key=key=>({key,preventDefault(){}});
inputHandlers.keydown(key('ArrowDown'));assert.equal(ctx.state.highlighted,1);
inputHandlers.keydown(key('ArrowUp'));assert.equal(ctx.state.highlighted,0);
inputHandlers.keydown(key('ArrowUp'));assert.equal(ctx.state.highlighted,ctx.state.visibleResults.length-1);
ctx.state.highlighted=0;inputHandlers.keydown(key('Enter'));assert.equal(navigation,'email');assert.equal(input.value,'');
ctx.state.activePanel='search';input.value='email';inputHandlers.input();inputHandlers.keydown(key('Escape'));
assert.equal(ctx.state.activePanel,'');assert.equal(panel.hidden,true);
input.value='hidden query';inputHandlers.input();assert.equal(panel.hidden,true);

const queries=['email','meta','certificate','analtyics','creative refresh','fulfillment','xyzxyz'];
const samples=[];
for(let i=0;i<1000;i++){const t=performance.now();ctx.rank(index,queries[i%queries.length]);samples.push(performance.now()-t);}
samples.sort((a,b)=>a-b);
console.log(JSON.stringify({entries:rows.length,mean_ms:samples.reduce((a,b)=>a+b)/samples.length,p95_ms:samples[950],max_ms:samples[999]}));
assert.ok(samples[950]<20,'Local ranking p95 should be below 20ms');
console.log('App search ranking, rendering, dismissal and navigation checks passed.');
