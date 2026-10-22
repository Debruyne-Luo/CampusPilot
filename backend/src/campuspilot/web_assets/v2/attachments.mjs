// Session-owned image drafts. The chat body contains attachment references only.
import { h } from "./dom.mjs";

export const IMAGE_LIMIT = 3;
export const IMAGE_BYTES = 10 * 1024 * 1024;
const TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const HEADERS = { "X-CampusPilot-Request": "1" };

export function imageProblem(file, count = 0) {
  if (count >= IMAGE_LIMIT) return "每条消息最多 3 张图片。";
  if (!TYPES.has(file?.type)) return "请选择 JPEG、PNG 或 WebP 图片。";
  if (!file.size || file.size > IMAGE_BYTES) return "每张图片需大于 0 且不超过 10MB。";
  return "";
}

/** Raw-binary upload with real progress. Synthetic tests inject an XHR implementation. */
export function uploadImage(file, progress = () => {}, { xhrFactory = () => new XMLHttpRequest(), signal } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = xhrFactory();
    const finish = (error, value) => { signal?.removeEventListener("abort", abort); error ? reject(error) : resolve(value); };
    const abort = () => xhr.abort();
    xhr.open("POST", "/api/attachments");
    xhr.withCredentials = true;
    xhr.timeout = 60000;
    xhr.setRequestHeader("Content-Type", file.type);
    xhr.setRequestHeader("X-CampusPilot-Request", "1");
    xhr.setRequestHeader("X-Attachment-Name", encodeURIComponent(file.name || "图片"));
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) progress(Math.round(100 * event.loaded / event.total)); };
    xhr.onload = () => {
      let body = {}; try { body = JSON.parse(xhr.responseText); } catch { /* invalid response */ }
      if (xhr.status >= 200 && xhr.status < 300 && typeof body.attachment_id === "string") finish(null, body);
      else finish(new Error(body.message || "图片上传失败，请重试。"));
    };
    xhr.onerror = () => finish(new Error("图片上传失败，请检查连接后重试。"));
    xhr.ontimeout = () => finish(new Error("图片上传超时，请重试。"));
    xhr.onabort = () => finish(new DOMException("已取消", "AbortError"));
    if (signal?.aborted) { finish(new DOMException("已取消", "AbortError")); return; }
    signal?.addEventListener("abort", abort, { once: true });
    xhr.send(file);
  });
}

export function createAttachmentComposer({ form, input, canEdit = () => true, onChange = () => {}, fetchImpl = fetch }) {
  let drafts = [], serial = 0, generation = 0, enabled = true;
  const host = h("div", { class: "attachment-drafts", "aria-label": "待发送图片", hidden: true });
  const notice = h("p", { class: "attachment-notice", role: "status", hidden: true });
  const picker = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", multiple: true, hidden: true, "aria-label": "选择校园图片" });
  const addButton = h("button", { type: "button", class: "attach-button", "aria-label": "添加照片、课表或通知图片", title: "添加图片（最多3张）", onclick: () => picker.click() }, "+ 图片");
  form.classList.add("has-attachments");
  form.prepend(host, notice, picker, addButton);

  const report = (message) => { notice.textContent = message; notice.hidden = !message; };
  const notify = () => { render(); onChange(); };
  function render() {
    host.hidden = !drafts.length;
    addButton.disabled = !enabled || !canEdit() || drafts.length >= IMAGE_LIMIT;
    host.replaceChildren(...drafts.map((d) => h("figure", { class: `attachment-draft ${d.status}` },
      h("img", { src: d.url, alt: d.file.name || "待发送图片" }),
      h("figcaption", {}, d.status === "uploading" ? `上传 ${d.progress}%` : d.status === "ready" ? "已就绪" : d.error || "上传失败"),
      d.status === "error" ? h("button", { type: "button", class: "attachment-retry", disabled: !canEdit(), onclick: () => upload(d) }, "重试") : null,
      h("button", { type: "button", class: "attachment-remove", "aria-label": `移除${d.file.name || "图片"}`, disabled: !canEdit(), onclick: () => remove(d) }, "×"))));
  }
  async function upload(d) {
    if (!enabled || !canEdit()) return;
    const started = generation;
    d.controller = new AbortController(); d.status = "uploading"; d.progress = 0; d.error = ""; notify();
    try {
      const data = await uploadImage(d.file, (percent) => { if (drafts.includes(d)) { d.progress = percent; render(); } }, { signal: d.controller.signal });
      if (started !== generation || !drafts.includes(d)) {
        // A removal can race with a successful server upload. Dispose the orphan reference.
        await erase(data.attachment_id); return;
      }
      d.attachment = data; d.status = "ready"; notify();
      // Fetch the normalized image through the protected endpoint, not an <img> URL.
      try {
        const response = await fetchImpl(`/api/attachments/${encodeURIComponent(data.attachment_id)}`, { headers: HEADERS, credentials: "same-origin" });
        if (response.ok) {
          const blob = await response.blob();
          if (started === generation && drafts.includes(d)) { URL.revokeObjectURL(d.url); d.url = URL.createObjectURL(blob); render(); }
        }
      } catch { /* the existing local preview remains usable */ }
    } catch (error) {
      if (started !== generation || !drafts.includes(d)) return;
      d.status = "error"; d.error = error.message || "上传失败"; notify();
    }
  }
  async function erase(id) {
    try { await fetchImpl(`/api/attachments/${encodeURIComponent(id)}`, { method: "DELETE", headers: HEADERS, credentials: "same-origin" }); } catch { /* server TTL is the cleanup fallback */ }
  }
  function remove(d) {
    if (!canEdit()) return;
    drafts = drafts.filter((x) => x !== d); d.controller?.abort(); URL.revokeObjectURL(d.url);
    if (d.attachment) erase(d.attachment.attachment_id);
    report(""); notify();
  }
  function add(files) {
    if (!enabled || !canEdit()) return;
    report("");
    for (const file of files) {
      const problem = imageProblem(file, drafts.length);
      if (problem) { report(problem); continue; }
      const draft = { id: ++serial, file, url: URL.createObjectURL(file), status: "uploading", progress: 0 };
      drafts.push(draft); upload(draft);
    }
    notify();
  }
  picker.addEventListener("change", () => { add(picker.files || []); picker.value = ""; });
  input.addEventListener("paste", (event) => {
    const files = [...(event.clipboardData?.items || [])].filter((item) => item.kind === "file" && item.type.startsWith("image/")).map((item) => item.getAsFile()).filter(Boolean);
    if (files.length) { event.preventDefault(); add(files); }
  });
  notify();
  return {
    get count() { return drafts.length; },
    get ready() { return drafts.every((d) => d.status === "ready"); },
    ids() { return drafts.filter((d) => d.status === "ready").map((d) => d.attachment.attachment_id); },
    previews() { return drafts.map((d) => ({ url: d.url, name: d.file.name || "图片" })); },
    refresh: notify,
    report,
    // Successful sends keep server attachments for follow-ups and previews in the thread.
    sent() { drafts = []; report(""); notify(); },
    clear() { generation++; for (const d of drafts) { d.controller?.abort(); URL.revokeObjectURL(d.url); } drafts = []; report(""); notify(); },
    setEnabled(value) { enabled = value; addButton.hidden = !value; notify(); },
  };
}
