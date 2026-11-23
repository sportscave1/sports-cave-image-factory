const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const ts = require('../shopify_customer_account/node_modules/typescript');
const dir = path.join(__dirname, '../shopify_customer_account/extensions/customer-certificate-vault/src');
const source = fs.readFileSync(path.join(dir, 'MySportsCaveCollection.jsx'), 'utf8');
const commerce = {exports: {}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(dir, 'account-commerce.js'), 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText, {module: commerce, exports: commerce.exports});

function setup(pairCache) {
  let finish, cleanup;
  const changes = [];
  const pending = new Promise(resolve => { finish = resolve; });
  const hooks = {useState: initial => [initial, value => changes.push(value)], useEffect: callback => { cleanup = callback(); }};
  const h = (type, props, ...children) => ({type, props, children});
  const jsx = (type, props) => h(type, props, props?.children);
  const module = {exports: {}};
  const compiled = ts.transpileModule(source + '\nvaultRequest = testRequest; export {CollectionUpsells};', {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, jsxFactory: 'h'}}).outputText;
  vm.runInNewContext(compiled, {module, exports: module.exports, testRequest: () => pending, AbortController, h, require: name => name === 'preact/jsx-runtime' ? {jsx, jsxs: jsx} : name === 'preact/hooks' ? hooks : name === './account-commerce.js' ? commerce.exports : name === './collection-performance.js' ? {timedOperation: (_a, _b, _o, work) => work()} : {}});
  const calls = [];
  const api = {query: async (query, variables) => { calls.push(variables); return {data: {nodes: [{id: 'two', handle: 'two', availableForSale: true}, {id: 'one', handle: 'one', availableForSale: false}, {id: 'three', handle: 'three', availableForSale: true}]}}; }};
  const tree = module.exports.CollectionUpsells({pairCache, api, apiBaseUrl: 'https://fixture.invalid', country: 'AU', certificate: {shopify_product_id: 'owned', product_title: 'Fixture'}});
  return {tree, finish, calls, changes, cleanup: () => cleanup()};
}

test('obsolete edition request never starts a Storefront query after it finishes', async () => {
  const f = setup();
  f.cleanup();
  f.finish({products: [{id: 'one'}]});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(f.calls.length, 0);
  assert.deepEqual(f.changes, ['loading']);
});

test('current edition rechecks Storefront availability and keeps two cards in smart rank', async () => {
  const f = setup();
  f.finish({products: [{id: 'one'}, {id: 'three'}, {id: 'two'}]});
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].variables.country, 'AU');
  const products = f.changes.find(Array.isArray);
  assert.deepEqual(Array.from(products, item => item.id), ['three', 'two']);
  assert.equal(f.changes.at(-1), 'ready');
});

const pairCacheModule = {exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(dir, 'collection-pair-cache.js'), 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{module:pairCacheModule,exports:pairCacheModule.exports});
test('completed pairs are reused only inside the bounded mounted-account cache and expire',()=>{
 let time=0;
 const first=pairCacheModule.exports.createCollectionPairCache({now:()=>time,ttl:30,maxEntries:2});
 const other=pairCacheModule.exports.createCollectionPairCache({now:()=>time});
 const key=JSON.stringify(['AU','owned-edition','owned-one']);
 const cards=[{id:'pair'}];first.put(key,cards);
 assert.equal(first.get(key),cards);assert.equal(other.get(key),undefined);
 assert.equal(first.get(JSON.stringify(['US','owned-edition','owned-one'])),undefined);
 assert.equal(first.get(JSON.stringify(['AU','owned-edition','new-purchase'])),undefined);
 time=30;assert.equal(first.get(key),undefined);
 first.put('a',cards);first.put('b',cards);first.get('a');first.put('c',cards);
 assert.equal(first.get('b'),undefined);assert.equal(first.get('a'),cards);
});
test('paired edition labels separate punctuation and preserve athlete apostrophes',()=>{
 for(const [input,title,athlete] of [
  ['All Rise — Aaron Judge Wall Art','All Rise','Aaron Judge'],
  ['"The Diesel"; "Shaquille O\'Neal" Wall Art','The Diesel',"Shaquille O'Neal"],
  ['It’s Like Fire - Mike Tyson','It’s Like Fire','Mike Tyson'],
  ['Edition : Athlete','Edition','Athlete'],
  ['Edition " Athlete','Edition','Athlete'],
  ['Unpunctuated Edition','Unpunctuated Edition',''],
 ])assert.deepEqual({...commerce.exports.pairedEditionTitle(input)},{title,athlete});
});
function find(node,predicate){
 if(Array.isArray(node)){for(const child of node){const match=find(child,predicate);if(match)return match;}return null;}
 if(!node||typeof node!=='object')return null;
 if(predicate(node))return node;
 return find(node.children||[],predicate);
}
test('pending recommendations show a spinner, while fresh cache hits render without new lookups',()=>{
 const pending=setup();
 assert.ok(find(pending.tree,n=>n.type==='s-spinner'&&n.props.accessibilityLabel==='Loading recommendations'));
 pending.cleanup();pending.finish({products:[]});
 const cache=pairCacheModule.exports.createCollectionPairCache();
 cache.put(JSON.stringify(['AU','owned','']),[{id:'pair',handle:'pair',title:'Edition — Athlete',availableForSale:true}]);
 const cached=setup(cache);
 assert.equal(cached.calls.length,0);assert.equal(cached.changes.at(-1),'ready');
 assert.equal(find(cached.tree,n=>n.type==='s-spinner'),null);
 assert.ok(find(cached.tree,n=>n.type==='s-link'));
 cached.cleanup();
});
