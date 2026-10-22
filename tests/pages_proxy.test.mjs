import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../deploy/pages/_worker.js';

const publicOrigin = 'https://cdutdino.pages.dev';
const origin = 'https://SYNTHETIC-origin.example';

test('Pages preserves paths, query, request body and same-origin browser authentication', async t => {
  t.mock.method(globalThis, 'fetch', async request => {
    assert.equal(request.url, origin.toLowerCase() + '/api/chat?synthetic=1');
    assert.equal(request.method, 'POST');
    assert.equal(request.headers.get('Origin'), origin.toLowerCase());
    assert.equal(request.headers.get('X-CampusPilot-Request'), '1');
    assert.equal(await request.text(), 'SYNTHETIC request');
    return new Response('SYNTHETIC answer', {headers: {
      'Set-Cookie': 'session=SYNTHETIC; HttpOnly; Secure; SameSite=Strict; Path=/',
      'Cache-Control': 'no-store',
    }});
  });
  const response = await worker.fetch(new Request(publicOrigin + '/api/chat?synthetic=1', {
    method: 'POST', body: 'SYNTHETIC request',
    headers: {Origin: publicOrigin, 'X-CampusPilot-Request': '1'},
  }), {CAMPUSPILOT_ORIGIN: origin});
  assert.equal(await response.text(), 'SYNTHETIC answer');
  assert.match(response.headers.get('Set-Cookie'), /HttpOnly/);
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
});

test('Pages preserves foreign origins so the backend can reject cross-site requests', async t => {
  t.mock.method(globalThis, 'fetch', async request => {
    assert.equal(request.headers.get('Origin'), 'https://SYNTHETIC-foreign.example');
    return new Response('SYNTHETIC denied', {status: 403});
  });
  const response = await worker.fetch(new Request(publicOrigin + '/api/session', {
    method: 'POST', headers: {Origin: 'https://SYNTHETIC-foreign.example'},
  }), {CAMPUSPILOT_ORIGIN: origin});
  assert.equal(response.status, 403);
});

test('Pages relays SSE without consuming or buffering the upstream stream', async t => {
  let controller;
  const stream = new ReadableStream({start(value) { controller = value; }});
  t.mock.method(globalThis, 'fetch', async () => new Response(stream, {
    headers: {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store'},
  }));
  const response = await worker.fetch(new Request(publicOrigin + '/api/chat/stream'), {});
  controller.enqueue(new TextEncoder().encode('event: SYNTHETIC\n\n'));
  const reader = response.body.getReader();
  const chunk = await reader.read();
  assert.equal(new TextDecoder().decode(chunk.value), 'event: SYNTHETIC\n\n');
  controller.close();
  assert.equal(response.headers.get('Content-Type'), 'text/event-stream');
});

test('Pages rewrites only origin-local redirects and exposes genuine upstream failures', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response(null, {
    status: 302, headers: {Location: origin + '/map-view'},
  }));
  const response = await worker.fetch(new Request(publicOrigin + '/'), {CAMPUSPILOT_ORIGIN: origin});
  assert.equal(response.headers.get('Location'), publicOrigin + '/map-view');
  t.mock.method(globalThis, 'fetch', async () => { throw new Error('SYNTHETIC TLS failure'); });
  assert.equal((await worker.fetch(new Request(publicOrigin), {})).status, 502);
});

test('Pages refuses malformed origin configuration', async () => {
  for (const value of ['http://SYNTHETIC.example', 'https://SYNTHETIC.example/extra', 'invalid']) {
    const response = await worker.fetch(new Request(publicOrigin), {CAMPUSPILOT_ORIGIN: value});
    assert.equal(response.status, 503);
  }
});

test('Double-slash request paths cannot turn Pages into a proxy to an arbitrary host', async t => {
  t.mock.method(globalThis, 'fetch', async request => {
    assert.equal(new URL(request.url).origin, origin.toLowerCase());
    assert.equal(new URL(request.url).pathname, '//SYNTHETIC-foreign.example/path');
    return new Response('SYNTHETIC bounded origin');
  });
  await worker.fetch(new Request(publicOrigin + '//SYNTHETIC-foreign.example/path'), {
    CAMPUSPILOT_ORIGIN: origin,
  });
});
