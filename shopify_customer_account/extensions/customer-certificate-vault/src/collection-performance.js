const OPERATIONS = new Set(['collection_orders', 'bootstrap', 'review_options', 'recommendations', 'frame_prices', 'pair_products']);
const reporters = new WeakMap();
const clock = () => globalThis.performance?.now?.() ?? Date.now();

export function createPerformanceReporter(send, schedule = setTimeout) {
  let samples = [], total = 0, scheduled = false;
  const flush = () => {
    scheduled = false;
    const batch = samples;
    samples = [];
    if (batch.length) Promise.resolve().then(() => send(batch)).catch(() => {});
  };
  return {
    record(operation, duration, outcome) {
      if (!OPERATIONS.has(operation) || !['ok', 'error', 'aborted'].includes(outcome) || !Number.isFinite(duration) || total >= 24) return;
      if (samples.length >= 12) return;
      samples.push({operation, duration_ms: Math.round(Math.min(120000, Math.max(0, duration))), outcome});
      total += 1;
      if (!scheduled) { scheduled = true; schedule(flush, 2000); }
    },
  };
}

export function operationForPath(path) {
  return ({'/api/collector-vault/bootstrap': 'bootstrap', '/api/collector-vault/review-prompt': 'review_options', '/api/collector-vault/recommendations': 'recommendations'})[path.split('?')[0]];
}

async function send(api, base, samples) {
  const token = await api.sessionToken.get();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  try {
    await fetch(`${base}/api/collector-vault/performance`, {method: 'POST', signal: controller.signal,
      headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'X-Sports-Cave-Request': 'customer-account-extension'},
      body: JSON.stringify({samples})});
  } finally { clearTimeout(timer); }
}

export async function timedOperation(api, base, operation, work) {
  const started = clock();
  let outcome = 'ok';
  try { return await work(); }
  catch (error) { outcome = error?.name === 'AbortError' ? 'aborted' : 'error'; throw error; }
  finally {
    try {
      if (OPERATIONS.has(operation)) {
        let entry = reporters.get(api);
        if (!entry || entry.base !== base) {
          entry = {base, reporter: createPerformanceReporter(samples => send(api, base, samples))};
          reporters.set(api, entry);
        }
        entry.reporter.record(operation, clock() - started, outcome);
      }
    } catch (_) { /* Optional diagnostics must never affect the operation. */ }
  }
}
