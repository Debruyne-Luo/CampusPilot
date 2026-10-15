import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import * as walk from '../backend/src/campuspilot/web_assets/v2/route-walk.mjs';

const source = readFileSync(new URL('../backend/src/campuspilot/web_assets/map-frame.js', import.meta.url), 'utf8');
// Synthetic L-shaped route; never represents a campus destination or device fix.
const path = [[0, 0], [0, .001], [.001, .001]];

function harness(overrides = {}) {
  const track = walk.buildTrack(path), start = walk.pointAt(track, 0);
  const poses = [], rotations = [], centers = [];
  let nextFrame;
  const state = {walk, track, demo: false, speed: 9, d: 0, shown: {...start},
    bearing: start.bearing, compass: null, gps: null, arrived: false, paused: false,
    last: 0, introUntil: 0, ...overrides};
  const context = vm.createContext({
    window: {addEventListener() {}}, parent: {postMessage() {}},
    location: {origin: 'https://test.invalid'}, matchMedia: () => ({matches: false}),
    performance: {now: () => 0}, document: {body: {dataset: {}}},
    requestAnimationFrame: callback => {nextFrame = callback; return 1;},
    fakeMap: {setRotation: value => rotations.push(value), setCenter: value => centers.push(value)},
    fakeGuide: {setPose: (pose, walking) => poses.push({...pose, walking})}, initialState: state,
  });
  vm.runInContext(source + '\nmap=fakeMap;guide=fakeGuide;dinoState=initialState;globalThis.tick=dinoFrame;', context);
  const tick = now => {
    const callback = nextFrame || context.tick;
    nextFrame = null;
    callback(now);
  };
  const finite = () => {
    assert.ok(poses.length > 0);
    assert.ok(poses.every(p => [p.lng, p.lat, p.bearing].every(Number.isFinite)), 'guide pose remains finite');
    assert.ok(rotations.every(Number.isFinite), 'map rotation remains finite');
    assert.ok(centers.every(p => p.every(Number.isFinite)), 'map center remains finite');
  };
  return {state, tick, finite, poses, rotations, centers};
}

test('waiting for GPS preserves guide pose and camera across consecutive animation frames', () => {
  const h = harness();
  for (let i = 0; i < 120; i++) h.tick(1000 + i * 16);
  h.finite();
  assert.equal(h.poses.length, 120);
  assert.ok(h.centers.length > 0);
  assert.ok(h.poses.every(p => p.lng === 0 && p.lat === 0 && p.bearing === 0 && !p.walking));
});

test('waiting for GPS preserves compass heading when compass updates stop', () => {
  const h = harness({compass: 90});
  for (let i = 0; i < 30; i++) h.tick(1000 + i * 16);
  const heading = h.state.bearing;
  h.state.compass = null;
  for (let i = 0; i < 60; i++) h.tick(1480 + i * 16);
  h.finite();
  assert.ok(heading > 0 && heading < 90);
  assert.equal(h.state.bearing, heading);
});

test('a GPS fix after waiting advances the guide along the route', () => {
  const h = harness();
  for (let i = 0; i < 10; i++) h.tick(1000 + i * 16);
  h.state.gps = [0, .0005];
  for (let i = 0; i < 30; i++) h.tick(1160 + i * 16);
  h.finite();
  assert.ok(h.state.d > 50 && h.state.d < 60);
  assert.ok(h.state.shown.lat > 0 && h.state.shown.lat <= .0005);
  assert.equal(h.state.bearing, 0);
});

test('GPS beyond the route retains the last heading', () => {
  const h = harness({gps: [.01, .01], bearing: 45});
  for (let i = 0; i < 30; i++) h.tick(1000 + i * 16);
  h.finite();
  assert.equal(h.state.bearing, 45);
  assert.ok(h.state.shown.lng > 0 && h.state.shown.lat > 0);
});

test('route demonstration advances, pauses, and resumes without GPS', () => {
  const h = harness({demo: true});
  for (let i = 0; i < 20; i++) h.tick(1000 + i * 16);
  const distance = h.state.d;
  assert.ok(distance > 0);
  h.state.paused = true;
  for (let i = 0; i < 20; i++) h.tick(1320 + i * 16);
  assert.equal(h.state.d, distance);
  assert.equal(h.poses.at(-1).walking, false);
  h.state.paused = false;
  h.tick(1640);
  assert.ok(h.state.d > distance);
  h.finite();
});
