import { test } from "node:test";
import assert from "node:assert/strict";
import { citedCount } from "../backend/src/campuspilot/web_assets/v2/render.mjs";

test("已核对引用 count matches the 引用来源 cards, not raw chunk+source ids", () => {
  assert.equal(citedCount({ source_ids: ["c1", "s1", "c2", "s1"], citations: [{ id: "s1" }, { id: "s2" }, { id: "s3" }] }), 3);
  assert.equal(citedCount({ source_ids: ["a", "a", "b"] }), 2); // no citations: unique ids
  assert.equal(citedCount({ citations: [] , source_ids: ["a"] }), 0);
  assert.equal(citedCount({}), 0); assert.equal(citedCount(null), 0);
});
