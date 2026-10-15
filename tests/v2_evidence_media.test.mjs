import test from "node:test";
import assert from "node:assert/strict";
import { ask } from "../backend/src/campuspilot/web_assets/v2/sse.mjs";
import { createAttachmentComposer, imageProblem, IMAGE_BYTES, uploadImage } from "../backend/src/campuspilot/web_assets/v2/attachments.mjs";
import { createPlaceSearch, navigationTarget } from "../backend/src/campuspilot/web_assets/v2/place-search.mjs";
import { answerBadge } from "../backend/src/campuspilot/web_assets/v2/render.mjs";

test("image validation rejects oversized, empty, fourth and unsupported images", () => {
  const valid = { type: "image/png", size: IMAGE_BYTES };
  assert.equal(imageProblem(valid, 2), "");
  assert.match(imageProblem(valid, 3), /最多/);
  assert.match(imageProblem({ ...valid, size: IMAGE_BYTES + 1 }), /10MB/);
  assert.match(imageProblem({ ...valid, size: 0 }), /10MB/);
  assert.match(imageProblem({ ...valid, type: "image/svg+xml" }), /JPEG/);
});

test("image feature switch hides controls and rejects pasted images", () => {
  class TestNode {
    constructor() { this.children = []; this.events = {}; this.attributes = {}; this.classList = { add() {} }; }
    setAttribute(k, v) { this.attributes[k] = v; }
    addEventListener(k, v) { this.events[k] = v; }
    append(...nodes) { this.children.push(...nodes); }
    prepend(...nodes) { this.children.unshift(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; }
  }
  const previousDocument = globalThis.document, previousNode = globalThis.Node;
  globalThis.Node = TestNode; globalThis.document = { createElement: () => new TestNode() };
  try {
    const form = new TestNode(), input = new TestNode();
    const composer = createAttachmentComposer({ form, input });
    composer.setEnabled(false);
    const control = form.children.find((n) => n.className === "attach-button");
    assert.equal(control.hidden, true);
    input.events.paste({ preventDefault() {}, clipboardData: { items: [{ kind: "file", type: "image/png", getAsFile: () => ({ type: "image/png", size: 50 }) }] } });
    assert.equal(composer.count, 0);
    composer.setEnabled(true);
    assert.equal(control.hidden, false);
    assert.equal(control.disabled, false);
  } finally { globalThis.document = previousDocument; globalThis.Node = previousNode; }
});

test("uploads send binary with browser boundary headers and surface actual progress", async () => {
  const calls = [], progress = [];
  const file = { name: "合成课表.png", type: "image/png", size: 50 };
  const xhr = { upload: {}, open: (...args) => calls.push(args), setRequestHeader: (...args) => calls.push(args),
    send(body) { assert.equal(body, file); this.upload.onprogress({ lengthComputable: true, loaded: 25, total: 50 }); this.status = 200; this.responseText = JSON.stringify({ attachment_id: "synthetic-image" }); this.onload(); } };
  assert.equal((await uploadImage(file, (n) => progress.push(n), { xhrFactory: () => xhr })).attachment_id, "synthetic-image");
  assert.deepEqual(progress, [50]);
  assert.ok(calls.some(([name, value]) => name === "X-CampusPilot-Request" && value === "1"));
  assert.ok(calls.some(([name, value]) => name === "X-Attachment-Name" && value === encodeURIComponent(file.name)));
});

test("pure image message and text fallback preserve the same attachment ids", async () => {
  const sent = [];
  const result = await ask("", () => {}, async (url, init) => {
    sent.push([url, JSON.parse(init.body)]);
    return url.endsWith("/stream") ? new Response("{}", { status: 404 }) : new Response(JSON.stringify({ answer: "Synthetic image answer" }), { status: 200 });
  }, { attachmentIds: ["synthetic-image"] });
  assert.equal(result.ok, true);
  assert.deepEqual(sent.map(([, body]) => body), [{ message: "", attachment_ids: ["synthetic-image"] }, { message: "", attachment_ids: ["synthetic-image"] }]);
});

test("cancelled chat does not start the fallback request", async () => {
  const controller = new AbortController(); controller.abort();
  const calls = [];
  const result = await ask("synthetic", () => {}, async (url) => { calls.push(url); throw new DOMException("aborted", "AbortError"); }, { signal: controller.signal });
  assert.deepEqual(calls, ["/api/chat/stream"]);
  assert.equal(result.body.error_code, "cancelled");
});

test("map search works without a map, protects header and ignores stale requests", async () => {
  const pending = [], sent = [];
  const service = createPlaceSearch(async (url, init) => { sent.push([url, init]); return await new Promise((resolve) => pending.push(resolve)); });
  const first = service.search("合成旧地点"), second = service.search("合成新地点");
  pending[1](new Response(JSON.stringify({ places: [{ place_id: "amap:poi:SYNTHETIC" }] }), { status: 200 }));
  assert.equal((await second).places.length, 1);
  pending[0](new Response(JSON.stringify({ places: [{ place_id: "old" }] }), { status: 200 }));
  assert.equal(await first, null);
  assert.equal(sent[0][0], "/api/places/search");
  assert.equal(sent[0][1].headers["X-CampusPilot-Request"], "1");
  assert.deepEqual(JSON.parse(sent[0][1].body), { query: "合成旧地点" });
  assert.equal(sent[0][1].signal.aborted, true);
});

test("navigation uses provider coordinates while directory records retain IDs", () => {
  const position = { longitude: 104.14, latitude: 30.67, coordinate_system: "GCJ02" };
  assert.deepEqual(navigationTarget({ place_id: "amap:poi:SYNTHETIC", position }), { position });
  assert.deepEqual(navigationTarget({ place_id: "cdut:place:synthetic", position }), { place_id: "cdut:place:synthetic" });
  assert.equal(answerBadge({ answer_mode: "agent_place" }), "已找到地点");
  assert.equal(answerBadge({ answer_mode: "agent_image" }), "图片内容");
});
