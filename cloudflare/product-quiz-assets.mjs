/** Public quiz delivery only. Bind QUIZ_ASSETS to the existing private R2 assets bucket.
 * No bucket listing, private assets, uploads, redirects, credentials or OS dependency.
 */
export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    const allowed = /^\/product-quiz\/(?:loader\.js|manifest\.json|catalogue\.json|(?:config|catalogue)\/[a-f0-9]{24}\.json|runtime\/[a-f0-9]{24}\.js)$/;
    const headers = new Headers({
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
      'Access-Control-Allow-Headers': 'If-None-Match',
      'Access-Control-Expose-Headers': 'ETag',
      'X-Content-Type-Options': 'nosniff',
    });
    const fail = (status, text) => {
      headers.set('Cache-Control', 'no-store');
      return new Response(text, { status, headers });
    };
    if (!allowed.test(path)) return fail(404, 'Not found');
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers });
    if (!['GET', 'HEAD'].includes(request.method)) return fail(405, 'Method not allowed');
    try {
      const object = await env.QUIZ_ASSETS.get(path.slice(1));
      if (!object) return fail(404, 'Not found');
      if (object.size > 250000) return fail(503, 'Asset unavailable');
      headers.set('Content-Type', path.endsWith('.js') ? 'text/javascript; charset=utf-8' : 'application/json; charset=utf-8');
      headers.set('Cache-Control', /\/[a-f0-9]{24}\./.test(path) ? 'public,max-age=31536000,immutable' : 'public,max-age=60,must-revalidate');
      headers.set('ETag', object.httpEtag);
      if (request.headers.get('If-None-Match') === object.httpEtag) return new Response(null, { status: 304, headers });
      return new Response(request.method === 'HEAD' ? null : object.body, { status: 200, headers });
    } catch {
      return fail(503, 'Asset unavailable');
    }
  },
};
