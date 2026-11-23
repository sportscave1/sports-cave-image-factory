import assert from 'node:assert/strict';
import test from 'node:test';
import {createPerformanceReporter, timedOperation, operationForPath} from '../shopify_customer_account/extensions/customer-certificate-vault/src/collection-performance.js';

test('metrics batch safely with fixed fields and a lifetime sample limit', async () => {
  const tasks = [], sent = [];
  const reporter = createPerformanceReporter(batch => sent.push(batch), callback => tasks.push(callback));
  reporter.record('private product title', 100, 'ok');
  assert.equal(tasks.length, 0);
  for (let i=0;i<30;i++) reporter.record('bootstrap', 130000, 'ok');
  assert.equal(tasks.length, 1);
  tasks.shift()();
  await Promise.resolve();
  assert.equal(sent[0].length, 12);
  assert.deepEqual(Object.keys(sent[0][0]).sort(), ['duration_ms', 'operation', 'outcome']);
  assert.equal(sent[0][0].duration_ms, 120000);
  for (let i=0;i<30;i++) reporter.record('pair_products', 200, 'ok');
  tasks.shift()();
  await Promise.resolve();
  assert.equal(sent.flat().length, 24);
  reporter.record('bootstrap', 100, 'ok');
  assert.equal(tasks.length, 0);
});

test('invalid durations and outcomes never schedule a report', () => {
  const tasks=[];
  const reporter=createPerformanceReporter(()=>{},callback=>tasks.push(callback));
  reporter.record('bootstrap', NaN, 'ok');
  reporter.record('bootstrap', 100, 'private error');
  assert.equal(tasks.length,0);
});

test('failed optional reporting cannot affect work or mask its original error', async () => {
  assert.equal(await timedOperation(null, '', 'bootstrap', async()=>42),42);
  const original=new Error('original');
  await assert.rejects(timedOperation(null, '', 'bootstrap', async()=>{throw original;}),error=>error===original);
  const tasks=[];
  const reporter=createPerformanceReporter(()=>Promise.reject(new Error('offline')),callback=>tasks.push(callback));
  reporter.record('bootstrap', 10, 'error');
  tasks[0]();
  await new Promise(resolve=>setImmediate(resolve));
});

test('only known read paths are measured, with all query parameters discarded', () => {
  assert.equal(operationForPath('/api/collector-vault/recommendations?product_id=private'),'recommendations');
  assert.equal(operationForPath('/api/collector-vault/frame/request'),undefined);
  assert.equal(operationForPath('/api/collector-vault/review'),undefined);
});
