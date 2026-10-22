import test from "node:test";
import assert from "node:assert/strict";
import { decisionCard } from "../backend/src/campuspilot/web_assets/v2/render.mjs";
import { experimentView } from "../backend/src/campuspilot/web_assets/v2/lab.mjs";

class TestNode {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; }
  setAttribute(k, v) { this.attributes[k] = v; }
  addEventListener() {}
  append(...children) { this.children.push(...children); }
  get textContent() { return this.children.map(c => c instanceof TestNode ? c.textContent : c).join(""); }
}

function dom(fn) {
  const saved = [globalThis.Node, globalThis.document];
  globalThis.Node = TestNode; globalThis.document = {createElement: t => new TestNode(t)};
  try { fn(); } finally { [globalThis.Node, globalThis.document] = saved; }
}

test("execution record shows actual decision status without raw prompts or private reasoning", () => dom(() => {
  assert.equal(decisionCard({}), null);
  const card = decisionCard({decisions:[{stage:"route",status:"timeout",action:"baseline",latency_ms:2000,raw:"SECRET"},
    {stage:"evidence",status:"ok",action:"insufficient",latency_ms:40}]});
  assert.equal(card.tag, "details");
  assert.match(card.textContent, /采用程序规划/);
  assert.match(card.textContent, /判断超时/);
  assert.match(card.textContent, /保留已知部分/);
  assert.doesNotMatch(card.textContent, /SECRET/);
}));

test("experiment viewer preserves failed/unknown cost and treats model text as text", () => dom(() => {
  const card = experimentView({status:"failed",title:"SYNTHETIC",question:"<script>alert(1)</script>",
    model:"fixture",knowledge_version:"fixture",cost_usd:null,stages:["base","probe"],trials:[{
      label:"baseline",answer:"SYNTHETIC answer",status:"limited",latency_ms:12,cost_usd:null,tools:[]}],
    changes:"SYNTHETIC",lessons:"",limitation:"Synthetic protocol test",code_identity:"fixture",
    upstream_commit:"1cfe254e8d25",adopted:false});
  assert.match(card.textContent, /未完成/);
  assert.match(card.textContent, /用量未确认/);
  assert.match(card.textContent, /尚未采用候选/);
  const all = n => [n,...n.children.filter(c => c instanceof TestNode).flatMap(all)];
  assert.ok(!all(card).some(n => n.tag === "script"));
}));
