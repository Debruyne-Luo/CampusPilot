// SYNTHETIC records only: no campus facts or real services.
import test from "node:test";
import assert from "node:assert/strict";
import { answerCards } from "../backend/src/campuspilot/web_assets/v2/render.mjs";

class TestNode {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener() {}
  append(...nodes) { this.children.push(...nodes); }
  get textContent() { return this.children.map((c) => c instanceof TestNode ? c.textContent : c).join(""); }
}
const descendants = (node) => [node, ...node.children.filter((c) => c instanceof TestNode).flatMap(descendants)];

test("guides show known facts, entrances and missing-procedure notice without fake numbered steps", () => {
  const oldNode = globalThis.Node, oldDocument = globalThis.document;
  globalThis.Node = TestNode; globalThis.document = { createElement: (tag) => new TestNode(tag) };
  try {
    for (const information_level of [undefined, "directory", "guide", "procedure"]) {
      const service = { information_level, name: "SYNTHETIC 测试服务", department: "SYNTHETIC 部门",
        audience: "SYNTHETIC 学生", entry_points: ["SYNTHETIC 入口"],
        contacts: [{ label: "SYNTHETIC 联系", value: "SYNTHETIC 公开信息" }],
        required_materials: ["SYNTHETIC 材料"], steps: [{ instruction: "SYNTHETIC 隐藏旧步骤" }],
        source_links: [{ title: "SYNTHETIC 依据", url: "https://example.org/synthetic" },
          { title: "unsafe", url: "javascript:alert(1)" }],
      };
      const cards = answerCards({ answer: "SYNTHETIC 回答", services: [service] }, {});
      const nodes = cards.flatMap(descendants), text = cards.map((n) => n.textContent).join("");
      assert.equal(nodes.some((n) => n.className === "numsteps"), information_level === "procedure");
      if (information_level !== "procedure") {
        assert.match(text, /SYNTHETIC 入口/); assert.match(text, /SYNTHETIC 公开信息/);
        assert.match(text, /完整办理流程尚未核验/); assert.doesNotMatch(text, /隐藏旧步骤/);
        assert.ok(nodes.some((n) => n.tag === "a" && n.textContent === "SYNTHETIC 依据"));
        assert.ok(!nodes.some((n) => n.attributes.href === "javascript:alert(1)"));
      }
    }
  } finally { globalThis.Node = oldNode; globalThis.document = oldDocument; }
});
