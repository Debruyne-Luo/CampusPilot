// Pages stays at cdutdino.pages.dev; only the HTTPS origin changes during migration.
const DEFAULT_ORIGIN = 'https://campuspilot.38-244-61-184.sslip.io:8443';

export default {
  async fetch(request, env) {
    let origin;
    try {
      origin = new URL(env.CAMPUSPILOT_ORIGIN || DEFAULT_ORIGIN);
      if (origin.protocol !== 'https:' || origin.username || origin.password
          || origin.pathname !== '/' || origin.search || origin.hash) throw new Error('origin');
    } catch {
      return new Response('CampusPilot origin is not configured correctly.', {status: 503});
    }
    const incoming = new URL(request.url);
    const target = new URL(origin.href);
    target.pathname = incoming.pathname;
    target.search = incoming.search;
    const headers = new Headers(request.headers);
    headers.set('Host', origin.host);
    // Rewrite only an actual same-origin browser request. Cross-site origins stay rejected.
    if (headers.get('Origin') === incoming.origin) headers.set('Origin', origin.origin);
    try {
      const upstream = await fetch(new Request(target, new Request(request, {headers})), {
        redirect: 'manual',
      });
      const responseHeaders = new Headers(upstream.headers);
      const location = responseHeaders.get('Location');
      if (location) {
        const redirect = new URL(location, target);
        if (redirect.origin === origin.origin) {
          responseHeaders.set('Location', incoming.origin + redirect.pathname + redirect.search);
        }
      }
      // Keep the upstream streaming body, status, session cookie and cache/security headers.
      return new Response(upstream.body, {
        status: upstream.status, statusText: upstream.statusText, headers: responseHeaders,
      });
    } catch {
      return new Response('CampusPilot origin is temporarily unavailable.', {
        status: 502, headers: {'Cache-Control': 'no-store'},
      });
    }
  },
};
