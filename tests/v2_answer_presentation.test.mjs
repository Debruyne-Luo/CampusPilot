// SYNTHETIC presentation fixtures, not university records.
import test from "node:test";
import assert from "node:assert/strict";
import { answerCards, answerBadge } from "../backend/src/campuspilot/web_assets/v2/render.mjs";

class TestNode {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener() {}
  append(...nodes) { this.children.push(...nodes); }
  get textContent() { return this.children.map(c => c instanceof TestNode ? c.textContent : c).join(""); }
}
const descendants = node => [node, ...node.children.filter(c => c instanceof TestNode).flatMap(descendants)];
function render(body, check) {
  const oldNode = globalThis.Node, oldDocument = globalThis.document;
  globalThis.Node = TestNode; globalThis.document = { createElement: tag => new TestNode(tag) };
  try { check(answerCards({ result_status: "success", ...body }, {}).flatMap(descendants)); }
  finally { globalThis.Node = oldNode; globalThis.document = oldDocument; }
}

test("completed answers render only paired inline bold and retain the full text and line breaks", () => {
  render({ answer: "SYNTHETIC **材料：**测试证件\n\n**下一步：**测试入口。未闭合**" }, nodes => {
    const paragraph = nodes.find(n => n.className === "conclusion");
    assert.equal(paragraph.textContent, "SYNTHETIC 材料：测试证件\n\n下一步：测试入口。未闭合**");
    assert.deepEqual(nodes.filter(n => n.tag === "strong").map(n => n.textContent), ["材料：", "下一步："]);
  });
});

test("HTML, URLs, empty and unmatched markers remain inert text", () => {
  for (const answer of ["", "**未闭合", "****", "**跨行\n标记**", "SYNTHETIC https://example.org/?a=<b>\n<img src=x onerror=alert(1)>"]) {
    render({ answer }, nodes => {
      assert.equal(nodes.find(n => n.className === "conclusion").textContent, answer);
      assert.equal(nodes.some(n => ["img", "script", "b", "strong"].includes(n.tag)), false);
    });
  }
  render({ answer: "**<script>alert(1)</script>**" }, nodes => {
    assert.equal(nodes.find(n => n.tag === "strong").textContent, "<script>alert(1)</script>");
    assert.equal(nodes.some(n => n.tag === "script"), false);
  });
});

test("zero citations are neutral, real counts and limited status remain distinct", () => {
  render({ citations: [] }, nodes => assert.equal(nodes.find(n => n.className === "kicker").textContent, "引用 0 条"));
  assert.equal(answerBadge({ citations: [] }), "引用 0 条");
  render({ source_ids: ["synthetic-a", "synthetic-a", "synthetic-b"] }, nodes =>
    assert.equal(nodes.find(n => n.className === "kicker").textContent, "已核对 · 引用 2 条"));
  render({ result_status: "limited", citations: [] }, nodes =>
    assert.equal(nodes.find(n => n.className === "kicker").textContent, "目前可确认的信息"));
});

test("answer paragraphs remain readable without losing amounts, exceptions or safe inline emphasis", () => {
  const answer = "**先做：**SYNTHETIC 测试操作。\n\n**注意：**余额大于20元，不是工本费。\n\n仅限合成对象；费用仍待核实。";
  render({ answer }, nodes => {
    assert.equal(nodes.find(n => n.className === "conclusion").textContent,
      answer.replaceAll("**", ""));
    assert.deepEqual(nodes.filter(n => n.className === "answer-paragraph").map(n => n.textContent), [
      "先做：SYNTHETIC 测试操作。", "注意：余额大于20元，不是工本费。", "仅限合成对象；费用仍待核实。",
    ]);
  });
});

test("preparation, conditions and detailed instructions are together in one closed procedure panel", () => {
  render({answer:"SYNTHETIC 简短结论",services:[{
    name:"SYNTHETIC procedure",information_level:"procedure",
    required_materials:["合成证件"],required_inputs:["合成编号"],
    limits:["仅限合成对象"],fees:["费用待核实"],notes:["来源适用范围待确认"],
    steps:[{instruction:"合成详细操作",condition:"合成适用条件"}],
  }]}, nodes => {
    const panels = nodes.filter(n => n.className === "card procedure-details");
    assert.equal(panels.length, 1);
    assert.equal(panels[0].tag, "details");
    assert.equal(panels[0].attributes.open, undefined);
    for (const text of ["查看办理步骤","合成证件","合成编号","合成详细操作","合成适用条件","仅限合成对象","费用待核实","来源适用范围待确认"]) {
      assert.ok(panels[0].textContent.includes(text), text);
    }
    assert.doesNotMatch(nodes.find(n=>n.className==="conclusion").textContent,/合成详细操作/);
  });
});
