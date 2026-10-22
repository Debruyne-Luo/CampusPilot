import { h } from "./dom.mjs";

const PHASES = {base:"基线执行",propose:"提出候选策略",probe:"候选试跑",compose:"综合配置",select:"选择产物",experience:"反思与经验记录",evaluate:"独立效果核验"};
const trialName = label => /^base/.test(label) ? "基线" : /^inv/.test(label) ? "通用策略候选" : /^dom/.test(label) ? "校园策略候选" : /^c\d/.test(label) ? "综合配置" : label;
export function experimentView(row) {
  const dollar = value => value == null ? "用量未确认" : `$${Number(value).toFixed(5)}`;
  const allTrials = row.trials || [];
  const primary = row.stages.includes("compose") ? allTrials.filter(t => /^base|^c\d|^final|^seq/.test(t.label)) : allTrials;
  const probes = allTrials.filter(t => !primary.includes(t));
  const trial = t => h("section", {class:"trial"},
    h("h3", {}, trialName(t.label)), h("p", {}, t.answer),
    h("p", {class:"meta"}, `${t.status} · ${(t.latency_ms / 1000).toFixed(2)} 秒 · ${dollar(t.cost_usd)}`),
    h("p", {class:"meta"}, `工具：${t.tools.join(" → ") || "无工具调用"}`));
  return h("div", {}, h("span", {class:"status"}, {running:"运行中",completed:"已完成",failed:"未完成",budget_exhausted:"预算已用尽"}[row.status]),
    h("h2", {}, row.title), h("p", {}, row.question),
    h("p", {class:"meta"}, `${row.model} · ${row.knowledge_version} · 累计预算占用 ${dollar(row.cost_usd)}`),
    h("p", {class:"conclusion"}, row.conclusion || "实验尚未完成，不代表质量提升。"),
    h("ol", {}, row.stages.map(s => h("li", {}, PHASES[s] || s))),
    h("div", {class:"trials"}, primary.map(trial)),
    probes.length ? h("details", {}, h("summary", {}, `其他候选试跑（${probes.length} 项）`), h("div", {class:"trials"}, probes.map(trial))) : null,
    h("details", {}, h("summary", {}, "策略发生了什么变化"), h("pre", {}, row.changes || "尚无配置变化")),
    h("details", {}, h("summary", {}, "积累的经验"), h("pre", {}, row.lessons || "尚无已保存经验")),
    h("p", {class:"notice"}, row.limitation),
    h("p", {class:"meta"}, `代码：${row.code_identity} · Harness² ${row.upstream_commit.slice(0,12)} · ${row.adopted ? "已采用配置" : "尚未采用候选"}`));
}

if (typeof document !== "undefined" && document.getElementById("experiments")) {
  const list = document.getElementById("experiments"), target = document.getElementById("experiment");
  let current = null, timer = null, requestId = 0;
  async function show(id) {
    const request = ++requestId;
    clearTimeout(timer);
    current = id;
    try {
      const response = await fetch(`/api/lab/experiments/${encodeURIComponent(id)}`, {cache:"no-store"});
      if (!response.ok) throw new Error("实验记录暂不可用");
      const row = await response.json();
      if (request !== requestId) return;
      target.replaceChildren(experimentView(row));
      for (const b of list.querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.id === current));
      if (row.status === "running") timer = setTimeout(() => show(id), 2500);
    } catch (error) { if (request === requestId) target.replaceChildren(h("p", {}, error.message)); }
  }
  fetch("/api/lab/experiments", {cache:"no-store"}).then(r => {if (!r.ok) throw new Error("无法读取实验列表"); return r.json();}).then(body => {
    list.replaceChildren(...body.experiments.map(row => h("button", {type:"button", "data-id":row.id, "aria-pressed":"false", onclick:() => show(row.id)}, row.title)));
    if (body.experiments.length) show((body.experiments.find(row => row.status === "completed") || body.experiments[0]).id);
    else target.replaceChildren(h("h2", {}, "还没有可展示的真实实验"), h("p", {}, "完成实验并导出公开记录后，结果会显示在这里。"));
  }).catch(() => target.replaceChildren(h("p", {}, "无法读取实验列表，请稍后重试。")));
  window.addEventListener("pagehide", () => {clearTimeout(timer); requestId++;});
}
