// Synthetic official-domain URLs exercise link contracts, not campus service claims.
import test from "node:test";
import assert from "node:assert/strict";
import { normalizeServiceLinks, safeServiceUrl, serviceLinkHints } from "../backend/src/campuspilot/web_assets/v2/service-links.mjs";
import { answerCards, planCard, serviceLinksCard } from "../backend/src/campuspilot/web_assets/v2/render.mjs";

const fixture = (kind = "online", extra = {}) => ({
  id: "synthetic-link", title: "合成测试事项", kind,
  url: `https://portal.cdut.edu.cn/synthetic-fixture/${kind}`,
  source_id: "synthetic-source", source_title: "合成测试原文",
  source_url: "https://www.cdut.edu.cn/synthetic-fixture/source",
  requires_login: true, network_requirement: "campus_or_vpn", availability: "not_checked", ...extra,
});

test("official destination validation accepts only HTTPS exact university hosts without credentials", () => {
  for (const url of ["https://cdut.edu.cn/synthetic", "https://portal.cdut.edu.cn/synthetic", "https://sub.portal.cdut.edu.cn/synthetic?next=%2Ftest", "https://CDUT.EDU.CN:443/synthetic"]) assert.ok(safeServiceUrl(url));
  for (const url of ["http://cdut.edu.cn/synthetic", "javascript:alert(1)", "//cdut.edu.cn/synthetic", "https://cdut.edu.cn.evil.example/", "https://evilcdut.edu.cn/", "https://cdut.edu.cn@evil.example/", "https://user:pass@portal.cdut.edu.cn/", "https://cdut.edu.cn:8443/", "https://cdut.edu.cn./", " https://cdut.edu.cn/", "https://cdut.edu.cn/\nsynthetic", "invalid", null, {}]) assert.equal(safeServiceUrl(url), null, String(url));
});

test("three link types have distinct actions and retain the exact source attribution", () => {
  const links = normalizeServiceLinks({ result_status: "success", service_links: [fixture("online"), fixture("platform"), fixture("guide")] });
  assert.deepEqual(links.map((s) => s.action_label), ["打开办理入口", "打开办事平台", "查看办事指南"]);
  assert.equal(links[0].source_id, "synthetic-source");
  assert.equal(links[0].source_url, "https://www.cdut.edu.cn/synthetic-fixture/source");
});

test("service URLs reject credential queries, unfinished paths and unsafe nested authentication returns", () => {
  for (const suffix of ["/fixture/*/apply", "/fixture/{id}", "/fixture/%257Bitem%257D", "/fixture;jsessionid=secret", "/fixture#fragment", "/fixture?ticket=synthetic", "/fixture?ACCESS_TOKEN=synthetic", "/fixture?%2574oken=synthetic", "/fixture?next=%2Fapply%3Ftoken%3Dsynthetic"]) assert.equal(safeServiceUrl(`https://portal.cdut.edu.cn${suffix}`), null, suffix);
  const nested = (url) => `https://sso.cdut.edu.cn/cas/login?service=${encodeURIComponent(encodeURIComponent(url))}`;
  for (const target of ["http://portal.cdut.edu.cn/fixture", "https://evil.example/fixture", "//evil.example/fixture", "javascript:alert(1)", "https://portal.cdut.edu.cn/fixture?ticket=synthetic", "https://portal.cdut.edu.cn/fixture/*", "https://portal.cdut.edu.cn/fixture%0A"]) assert.equal(safeServiceUrl(nested(target)), null, target);
  assert.ok(safeServiceUrl(nested("https://portal.cdut.edu.cn/synthetic-fixture/apply")));
  assert.ok(safeServiceUrl("https://portal.cdut.edu.cn/synthetic-fixture?next=%2Fapply"));
  for (const key of ["username", "user_id", "userid", "student_id", "studentid", "account", "authorization", "auth_token", "code", "credential"]) assert.equal(safeServiceUrl(`https://portal.cdut.edu.cn/synthetic-fixture?${key}=synthetic`), null, key);
  for (const key of ["service", "next", "return_url", "redirect_uri"]) assert.equal(safeServiceUrl(`https://sso.cdut.edu.cn/cas/login?${key}=`), null, `empty ${key}`);
  let excessive = "https://portal.cdut.edu.cn/synthetic-fixture";
  for (let i = 0; i < 5; i++) excessive = `https://sso.cdut.edu.cn/cas/login?service=${encodeURIComponent(excessive)}`;
  assert.equal(safeServiceUrl(excessive), null);
});

test("login and network requirements distinguish known conditions from unknown", () => {
  assert.deepEqual(serviceLinkHints(fixture()), ["需学校账号登录", "校外可能需校园网或 VPN"]);
  assert.deepEqual(serviceLinkHints(fixture("guide", { requires_login: null, network_requirement: "unknown" })), ["登录条件未核实", "网络条件未核实"]);
  assert.deepEqual(serviceLinkHints(fixture("guide", { requires_login: false, network_requirement: "unknown" })), ["网络条件未核实"]);
});

test("legacy, malformed, empty and refusal responses cannot display service links", () => {
  for (const body of [undefined, {}, { service_links: [] }, { service_links: {} }, { service_links: [null, "bad", fixture("unsupported"), fixture("__proto__"), fixture("online", { url: "https://evil.example/" }), fixture("online", { source_url: "javascript:alert(1)" })] }]) assert.deepEqual(normalizeServiceLinks(body), []);
  for (const result_status of ["empty", "out_of_scope", "unavailable", "refused", "error", "needs_clarification"]) assert.deepEqual(normalizeServiceLinks({ result_status, service_links: [fixture()] }), []);
  assert.equal(normalizeServiceLinks({ result_status: "limited", service_links: [fixture(), fixture()] }).length, 1);
});

class TestNode {
  constructor(tag) { this.tag = tag; this.children = []; this.attributes = {}; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener() {}
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  get textContent() { return this.children.map((c) => c instanceof TestNode ? c.textContent : c).join(""); }
}
const descendants = (node) => [node, ...node.children.filter((c) => c instanceof TestNode).flatMap(descendants)];

test("external platforms need a school source; direct URL helper remains school-only", () => {
  const url = "https://cet-bm.neea.edu.cn/";
  assert.equal(safeServiceUrl(url), null);
  assert.equal(normalizeServiceLinks({ service_links: [fixture("platform", { url })] })[0].url, url);
  assert.deepEqual(normalizeServiceLinks({ service_links: [fixture("platform", { url, source_url: "https://evil.example/" })] }), []);
});

test("steps and completed progress are folded; material expansion is explicitly offered", () => {
  const previousNode = globalThis.Node, previousDocument = globalThis.document;
  globalThis.Node = TestNode; globalThis.document = { createElement: (tag) => new TestNode(tag) };
  try {
    const body = { answer: "SYNTHETIC next action", result_status: "success", services: [{
      service_id: "synthetic:service", name: "SYNTHETIC service", information_level: "procedure",
      steps: [{ instruction: "SYNTHETIC detail" }],
    }], places: [{ name: "SYNTHETIC place" }] };
    const cards = answerCards(body, { onDetails: () => {} });
    const heading = descendants(cards[0]).find((n) => n.tag === "h2");
    assert.equal(heading.textContent, "SYNTHETIC service");
    assert.ok(cards.some((n) => n.tag === "button" && n.textContent === "查看材料与步骤"));
    const steps = cards.find((n) => n.textContent.includes("SYNTHETIC detail"));
    assert.equal(steps.tag, "details");
    assert.equal(steps.attributes.open, undefined);
    assert.equal(planCard({ done: true, steps: [] }).tag, "details");
    assert.equal(planCard({ done: false, steps: [] }).tag, "section");
  } finally { globalThis.Node = previousNode; globalThis.document = previousDocument; }
});

test("independent card shows actions, provenance and unverified availability without claiming completion", () => {
  const previousNode = globalThis.Node, previousDocument = globalThis.document;
  globalThis.Node = TestNode; globalThis.document = { createElement: (tag) => new TestNode(tag) };
  try {
    const body = { answer: "合成回答", result_status: "success", service_links: [fixture("online"), fixture("platform"), fixture("guide")] };
    const card = serviceLinksCard(body);
    assert.equal(card.attributes["aria-label"], "网上办理");
    assert.match(card.textContent, /需学校账号登录/);
    assert.match(card.textContent, /校外可能需校园网或 VPN/);
    assert.match(card.textContent, /当前可用性未核实/);
    const anchors = descendants(card).filter((n) => n.tag === "a");
    assert.deepEqual(anchors.filter((n) => n.className === "chip go").map((n) => n.textContent), ["打开办理入口", "打开办事平台", "查看办事指南"]);
    assert.equal(anchors.filter((n) => n.textContent === "查看入口依据").length, 3);
    assert.ok(anchors.every((n) => n.attributes.target === "_blank" && n.attributes.rel === "noopener noreferrer"));
    assert.ok(answerCards(body, {}).some((n) => n.attributes["aria-label"] === "网上办理"));
    assert.equal(serviceLinksCard({ result_status: "empty", service_links: [fixture()] }), null);
  } finally { globalThis.Node = previousNode; globalThis.document = previousDocument; }
});
