import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../cloudflare/product-quiz-assets.mjs';

test('only exact public quiz objects can reach private R2', async () => {
  const keys = [];
  const env = {QUIZ_ASSETS:{get:async key=>{keys.push(key);return {size:2,httpEtag:'"quiz"',body:'{}'};}}};
  for (const path of ['/','/product-quiz/','/exports/private.pdf','/product-quiz/../exports/private.pdf','/product-quiz/%2e%2e/exports/private.pdf','/product-quiz/config/private.json','/product-quiz/catalogue/../private.json']) {
    assert.equal((await worker.fetch(new Request('https://quiz.example.test'+path),env)).status,404);
  }
  assert.deepEqual(keys,[]);
  const response = await worker.fetch(new Request('https://quiz.example.test/product-quiz/manifest.json'),env);
  assert.equal(response.status,200);assert.deepEqual(keys,['product-quiz/manifest.json']);
  assert.equal(response.headers.get('Access-Control-Allow-Origin'),'*');
  assert.equal(response.headers.get('Cache-Control'),'public,max-age=60,must-revalidate');
  assert.equal(await response.text(),'{}');
});

test('immutable caching, conditional requests, HEAD and method restrictions', async () => {
  const url='https://quiz.example.test/product-quiz/runtime/'+'a'.repeat(24)+'.js';
  let reads=0;
  const env={QUIZ_ASSETS:{get:async()=>{reads++;return {size:2,httpEtag:'"quiz"',body:'OK'};}}};
  assert.equal((await worker.fetch(new Request(url,{method:'POST'}),env)).status,405);
  assert.equal((await worker.fetch(new Request(url,{method:'OPTIONS'}),env)).status,204);
  assert.equal(reads,0);
  const head=await worker.fetch(new Request(url,{method:'HEAD'}),env);
  assert.equal(head.status,200);assert.equal(await head.text(),'');
  assert.match(head.headers.get('Cache-Control'),/immutable/);
  const conditional=await worker.fetch(new Request(url,{headers:{'If-None-Match':'"quiz"'}}),env);
  assert.equal(conditional.status,304);
});

test('R2 failures and oversized objects fail closed', async () => {
  const request=new Request('https://quiz.example.test/product-quiz/catalogue.json');
  assert.equal((await worker.fetch(request,{QUIZ_ASSETS:{get:async()=>null}})).status,404);
  assert.equal((await worker.fetch(request,{QUIZ_ASSETS:{get:async()=>({size:250001})}})).status,503);
  assert.equal((await worker.fetch(request,{QUIZ_ASSETS:{get:async()=>{throw Error('private credentials');}}})).status,503);
});
