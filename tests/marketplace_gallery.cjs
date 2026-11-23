// Exercise gallery interaction without a browser, app startup or network access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

let pauses = 0;
let focused = -1;
const video = {pause() { pauses++; }, play() { throw new Error('The gallery must never autoplay.'); }};
const panels = [0, 1, 2].map(index => ({hidden: false, querySelector() { return index === 2 ? video : null; }}));
const links = panels.map((_, index) => ({
  events: {}, attributes: {},
  addEventListener(name, callback) { this.events[name] = callback; },
  setAttribute(name, value) { this.attributes[name] = value; },
  removeAttribute(name) { delete this.attributes[name]; },
  focus() { focused = index; }
}));
const caption = {};
const gallery = {
  querySelectorAll(selector) { return selector === '[data-media-panel]' ? panels : links; },
  querySelector() { return caption; }
};
const document = {
  querySelectorAll(selector) { return selector === '[data-gallery]' ? [gallery] : []; },
  querySelector() { return null; }
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/marketplace/marketplace.js'), 'utf8'), {document});

assert.deepEqual(panels.map(panel => panel.hidden), [false, true, true]);
assert.equal(caption.textContent, 'Photo 1 of 2');
links[2].events.click({preventDefault() {}});
assert.deepEqual(panels.map(panel => panel.hidden), [true, true, false]);
assert.equal(caption.textContent, 'Recorded item video');
assert.equal(links[2].attributes['aria-current'], 'true');
const before = pauses;
links[2].events.keydown({key: 'ArrowRight', preventDefault() {}});
assert.equal(focused, 0);
assert.equal(pauses, before + 1);
assert.equal(links[2].attributes['aria-current'], undefined);
assert.equal(caption.textContent, 'Photo 1 of 2');
links[0].events.keydown({key: 'End', preventDefault() {}});
assert.equal(focused, 2);
links[2].events.keydown({key: 'Home', preventDefault() {}});
assert.equal(focused, 0);
links[0].events.keydown({key: 'ArrowLeft', preventDefault() {}});
assert.equal(focused, 2);
console.log('Gallery: selection, keyboard navigation, video pause and no autoplay passed.');
