const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const ts = require('../shopify_customer_account/node_modules/typescript');

test('account photos retain native upload while video uses a separate storefront form', () => {
  const source = fs.readFileSync(path.join(__dirname, '../shopify_customer_account/extensions/customer-certificate-vault/src/AccountReview.jsx'), 'utf8');
  const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, jsxFactory: 'h'}}).outputText;
  const module = {exports: {}};
  const h = (type, props, ...children) => ({type, props: props || {}, children: children.flat(Infinity).filter(Boolean)});
  const hooks = {useState: value => [value, () => {}], useEffect: () => {}, useRef: value => ({current: value})};
  const jsx = (type, props) => h(type, props, props?.children);
  vm.runInNewContext(code, {module, exports: module.exports, h, require: name => name === 'preact/jsx-runtime' ? {jsx, jsxs: jsx} : name === 'preact/hooks' ? hooks : name === './collection-image-utils.js' ? {collectionThumbnail: value => value} : name === './account-review-utils.js' ? {reviewProductId: () => 'fixture'} : {}});
  const tree = module.exports.AccountReview({prompt: {reference: 'private-reference', product_title: 'Fixture'}, certificate: {}, request: () => assert.fail('must not submit while rendering'), api: {}});
  const all = [];
  function walk(n) { if (!n || typeof n !== 'object') return; all.push(n); (n.children || []).forEach(walk); }
  walk(tree);
  assert.ok(all.some(n => n.children.includes('Add photo/video (optional)')));
  const photo = all.find(n => n.type === 's-drop-zone');
  assert.equal(photo.props.label, 'Add photo');
  assert.doesNotMatch(photo.props.accept, /video|mp4/);
  const video = all.find(n => n.type === 's-button' && n.children.includes('Add video'));
  assert.equal(video.props.target, '_blank');
  assert.equal(video.props.href, 'https://www.sportscaveshop.com/pages/reviews#judgeme_review_widget');
  assert.doesNotMatch(video.props.href, /private-reference|email|customer/);
  assert.ok(all.some(n => n.children.includes('For video, open Write a review in the new tab and finish your review there.')));
});
