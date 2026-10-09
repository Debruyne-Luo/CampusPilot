// SYNTHETIC coordinates and timestamps: no real user locations or campus roads.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {create} = require('../backend/src/campuspilot/web_assets/guidance.js');
const geometry = [[1,1],[1.001,1],[1.002,1],[1.003,1],[1.004,1]];
const tracker = () => create(geometry,[1,3,4],440);
test('distance and instruction advance along a walking route',() => {
  const t=tracker(); const first=t.update([1,1],5,0), next=t.update([1.0011,1],5,60000);
  assert.equal(first.status,'walking'); assert.equal(next.step,1); assert.ok(next.remaining < first.remaining);
});
test('poor accuracy cannot advance progress or announce arrival',() => {
  const t=tracker(); t.update([1,1],5,0);
  assert.equal(t.update([1.004,1],100,10000).status,'inaccurate');
  assert.equal(t.update([1,1],5,20000).step,0);
});
test('one off-route fix is insufficient; sustained deviation prompts replanning',() => {
  const t=tracker(); assert.equal(t.update([1,1.002],5,0).status,'checking');
  assert.equal(t.update([1,1.002],5,7000).status,'off_route');
  assert.equal(t.update([1,1],5,14000).status,'walking');
});
test('nearby destination requires two accurate fixes separated in time',() => {
  const t=tracker(); assert.equal(t.update([1.004,1],5,0).status,'walking');
  assert.equal(t.update([1.004,1],5,2000).status,'walking');
  assert.equal(t.update([1.004,1],5,7000).status,'arrived');
});
test('a jump to a later segment cannot immediately skip instructions',() => {
  const t=tracker(); t.update([1,1],5,0);
  assert.equal(t.update([1.0015,1],5,2000).status,'unstable');
});
test('invalid fixes and malformed geometry are rejected',() => {
  assert.equal(tracker().update([NaN,1],5,0).status,'invalid');
  assert.throws(()=>create([[1,1],[1,1]],[1],10));
  assert.throws(()=>create(geometry,[99],440));
  assert.throws(()=>create(geometry,[3,1],440));
});
