// Pure reducer: stream events -> visible plan progress.
const LABELS = { understanding: "理解问题", composing: "组织答案并核对引用" };
const INTENT = { "办事": "办事", "找人": "找老师", "找地点": "找地点", "路线": "路线", "政策问答": "查资料", "闲聊": "闲聊" };

export function initialPlan() { return { steps: [], answer: "", done: false }; }

function upsert(steps, key, patch) {
  const i = steps.findIndex((s) => s.key === key);
  if (i < 0) return [...steps, { key, status: "running", meta: "", ...patch }];
  return steps.map((s, j) => (j === i ? { ...s, ...patch } : s));
}
const finishRunning = (steps) => steps.map((s) => (s.status === "running" ? { ...s, status: "empty", meta: "未完成" } : s));

export function reducePlan(state, { event, data }) {
  let steps = state.steps;
  switch (event) {
    case "understanding": {
      const meta = [INTENT[data.intent] || data.intent, data.slots?.service || data.slots?.destination].filter(Boolean).join(" · ");
      steps = upsert(steps, "understanding", { label: LABELS.understanding, status: "done", meta });
      break;
    }
    case "plan":
      for (const s of data.steps || []) {
        const key = `tool:${s.tool}`;
        if (!steps.some((x) => x.key === key)) steps = [...steps, { key, label: s.label, status: "pending", meta: "" }];
      }
      break;
    case "tool_start":
      steps = upsert(finishRunning(steps), `tool:${data.tool}`, { label: data.label, status: "running" });
      break;
    case "tool_end": {
      const ok = ["success", "done", "grounded"].includes(data.status);
      const meta = { empty: "无结果", skipped: "跳过", timeout: "超时", not_configured: "尚未配置", quota_exceeded: "额度受限", unavailable: "暂不可用", limited: "部分信息", budget: "额度受限" }[data.status] || "未完成";
      steps = upsert(steps, `tool:${data.tool}`, { label: data.label, status: ok ? "done" : "empty", meta: ok ? "" : meta });
      break;
    }
    case "composing":
      steps = upsert(finishRunning(steps), "composing", { label: data.label || LABELS.composing, status: "running" });
      break;
    case "answer_delta":
      return { ...state, steps, answer: state.answer + (data.text || "") };
    case "final":
      steps = steps.map((s) => {
        if (s.status === "pending") return { ...s, status: "skipped" };
        if (s.status !== "running") return s;
        const completed = s.key === "composing" && !data.degraded_reason;
        return { ...s, status: completed ? "done" : "empty", meta: completed ? "" : "未完成" };
      });
      return { ...state, steps, done: true };
    default:
      return state;
  }
  return { ...state, steps };
}
