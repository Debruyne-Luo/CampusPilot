// Server-sent events over fetch (POST): incremental parser + stream with /api/chat fallback.
export function parseSSE(buffer) {
  const events = [];
  const blocks = buffer.split(/\r?\n\r?\n/);
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    let event = "message";
    const data = [];
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (!data.length) continue;
    try { events.push({ event, data: JSON.parse(data.join("\n")) }); } catch { /* skip malformed */ }
  }
  return { events, rest };
}

const HEADERS = { "Content-Type": "application/json", "X-CampusPilot-Request": "1" };

/** Ask a question. Streams via /api/chat/stream; falls back to /api/chat when the stream
 *  is unavailable (404/405/network) before any event arrived. Resolves to the final body. */
export async function ask(message, onEvent, fetchImpl = fetch, { attachmentIds = [], signal } = {}) {
  let got = false;
  const payload = { message, ...(attachmentIds.length ? { attachment_ids: attachmentIds } : {}) };
  try {
    const res = await fetchImpl("/api/chat/stream", {
      method: "POST", headers: HEADERS, credentials: "same-origin", body: JSON.stringify(payload), signal,
    });
    if (res.ok && res.body && (res.headers.get("content-type") || "").includes("text/event-stream")) {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "", final = null;
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        const parsed = parseSSE(buffer + decoder.decode(value, { stream: true }));
        buffer = parsed.rest;
        for (const e of parsed.events) {
          got = true; onEvent(e);
          if (e.event === "final") final = e.data;
        }
      }
      if (final) return { ok: true, status: 200, body: final, streamed: true };
      if (got) return { ok: false, status: 0, body: { message: "连接中断，请重试。" }, streamed: true };
    } else if (![404, 405].includes(res.status)) {
      return { ok: false, status: res.status, body: await res.json().catch(() => ({})), streamed: false };
    }
  } catch {
    if (signal?.aborted) return { ok: false, status: 0, body: { error_code: "cancelled", message: "对话已取消。" }, streamed: got };
    if (got) return { ok: false, status: 0, body: { message: "连接中断，请重试。" }, streamed: true };
  }
  try {
    const res = await fetchImpl("/api/chat", {
      method: "POST", headers: HEADERS, credentials: "same-origin", body: JSON.stringify(payload), signal,
    });
    const body = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, body, streamed: false };
  } catch {
    return { ok: false, status: 0, body: { message: "连接中断，请重试。" }, streamed: false };
  }
}
