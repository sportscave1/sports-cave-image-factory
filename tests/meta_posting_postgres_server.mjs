// Disposable local PostgreSQL; never connects to production or Meta.
import {PGlite} from './fixtures/crm/node_modules/@electric-sql/pglite/dist/index.js';
import {readFileSync} from 'node:fs';
import http from 'node:http';
const db = new PGlite();
for (const name of ['20260626_ads_intelligence_v1', '20260626_ads_intelligence_v2_breakdowns',
  '20260626_ads_product_mapping_v1', '20260707_marketing_factory_copy_packs',
  '20260831_meta_posting_v1', '20260901_meta_posting_v2',
  '20260901_meta_posting_v3', '20260903_meta_posting_customer_lifecycle',
  '20260903_meta_posting_carousel', '20260903_meta_posting_run_identity']) {
  await db.exec(readFileSync(`migrations/${name}.sql`, 'utf8'));
}
let queue = Promise.resolve();
const server = http.createServer(async (req, res) => {
  if (req.method !== 'POST') { res.writeHead(405).end(); return; }
  let body = ''; for await (const part of req) body += part;
  const run = async () => {
    try {
      const {sql, args = []} = JSON.parse(body);
      const result = await db.query(sql, args);
      res.writeHead(200, {'content-type': 'application/json'}).end(JSON.stringify(result));
    } catch (error) {
      res.writeHead(400, {'content-type': 'application/json'}).end(JSON.stringify({error: error.message}));
    }
  };
  queue = queue.then(run, run);
});
server.listen(8890, '127.0.0.1', () => console.log('Meta posting PostgreSQL fixture ready'));
