const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const ts = require('../shopify_customer_account/node_modules/typescript');
const dir = path.join(__dirname, '../shopify_customer_account/extensions/customer-certificate-vault/src');
const source = fs.readFileSync(path.join(dir, 'MySportsCaveCollection.jsx'), 'utf8');
const commerce = {exports: {}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(dir, 'account-commerce.js'), 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText, {module: commerce, exports: commerce.exports});

function setup() {
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
  module.exports.CollectionUpsells({api, apiBaseUrl: 'https://fixture.invalid', country: 'AU', certificate: {shopify_product_id: 'owned', product_title: 'Fixture'}});
  return {finish, calls, changes, cleanup: () => cleanup()};
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
