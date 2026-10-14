import test from 'node:test';
import assert from 'node:assert/strict';
import { ask } from '../backend/src/campuspilot/web_assets/v2/sse.mjs';

test('offline fallback resolves an actionable failure so the composer can recover', async () => {
  let calls = 0;
  const result = await ask('synthetic', () => {}, async () => { calls++; throw new TypeError('offline'); });
  assert.equal(calls, 2);
  assert.equal(result.ok, false);
  assert.match(result.body.message, /网络连接失败/);
});

test('a stream interrupted after a partial answer never repeats the request via fallback', async () => {
  let calls = 0; const events = [];
  const result = await ask('synthetic', e => events.push(e), async () => {
    calls++;
    return new Response('event: answer_delta\ndata: {"text":"SYNTHETIC partial"}\n\n', {headers:{'Content-Type':'text/event-stream'}});
  });
  assert.equal(calls, 1);
  assert.equal(result.ok, false);
  assert.equal(result.streamed, true);
  assert.equal(events[0].data.text, 'SYNTHETIC partial');
});
