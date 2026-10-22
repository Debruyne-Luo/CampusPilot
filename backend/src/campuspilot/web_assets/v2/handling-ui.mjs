import {enterDesktop, isDesktop} from './desktop-motion.mjs';
import { h } from "./dom.mjs";
import { hasPosition } from "./places.mjs";
import { preparationLabel, sourceUrl, taskSnapshot } from "./handling-store.mjs";

const MODES = { online: "线上办理", self_service: "自助办理", in_person: "窗口办理" };

/** List/detail replace the thread visually, without destroying the conversation DOM. */
export function createHandlingUI({ store, entry, panel, toast, thread, form, getPlaces, getLegacyTicks, onExpand, onFocus, onGo }) {
  let view = "chat", selected = null, chatScroll = 0, listScroll = 0, returnFocus = null, timer;
  const previews = new Set();
  function dismissToast() { clearTimeout(timer); toast.hidden = true; toast.replaceChildren(); }
  function message(text, undo) {
    clearTimeout(timer);
    toast.replaceChildren(h("span", {}, text));
    if (undo) toast.append(h("button", { type: "button", class: "text-button", onclick: undo }, "撤销"));
    toast.hidden = false;
    const expire = () => {
      if (toast.matches(":focus-within, :hover")) timer = setTimeout(expire, 1000);
      else dismissToast();
    };
    timer = setTimeout(expire, 5000);
  }
  function focusHeading() { panel.querySelector("h2")?.focus({ preventScroll: true }); }
  function show(next, id = null) {
    if (view === "chat" && next !== "chat") { chatScroll = thread.scrollTop; returnFocus = document.activeElement; }
    if (view === "list" && next === "detail") listScroll = panel.querySelector(".handling-scroll")?.scrollTop || 0;
    view = next; selected = id;
    thread.hidden = next !== "chat"; form.hidden = next !== "chat"; panel.hidden = next === "chat";
    entry.setAttribute("aria-expanded", String(next !== "chat"));
    onExpand();
    if (next === "chat") {
      thread.scrollTop = chatScroll;
      if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
      else entry.focus({ preventScroll: true });
    } else { render(); focusHeading(); if(isDesktop())enterDesktop(panel.children,.18,8); }
  }
  function open(id = null) {
    show(id ? "detail" : "list", id);
    if (store.notice()) message("仅保存在此浏览器，清除网站数据后将丢失。");
  }
  function remove(task, completed) {
    const result = store.remove(task.service_id);
    if (!result.ok) { message(result.message); return; }
    show("list");
    message(completed ? "已标记办完" : "已移出清单", () => undoRestore(result.task));
  }
  function undoRestore(task) {
    const result = store.restore(task);
    if (!result.ok) { message(result.message, () => undoRestore(task)); return; }
    dismissToast(); show("detail", task.service_id);
  }
  function toolbar(title, back, task) {
    return h("div", { class: "handling-toolbar" },
      h("button", { type: "button", class: "handling-back", onclick: () => show(back) }, back === "chat" ? "‹ 返回对话" : "‹ 返回清单"),
      h("h2", { tabindex: "-1" }, title),
      task ? h("details", { class: "handling-menu" }, h("summary", { "aria-label": "事务操作" }, "⋯"),
        h("button", { type: "button", onclick: () => remove(task, false) }, "移除事务")) : null);
  }
  function renderList() {
    const tasks = store.list();
    const content = h("div", { class: "handling-scroll" }, tasks.length
      ? h("ul", { class: "handling-list" }, tasks.map((t) => h("li", {},
        h("button", { type: "button", class: "handling-row", onclick: () => show("detail", t.service_id) },
          h("b", {}, t.title), h("small", {}, preparationLabel(t)), h("span", { "aria-hidden": "true" }, "›")))))
      : h("div", { class: "handling-empty" }, h("span", { "aria-hidden": "true", class: "handling-empty-icon" }, "✓"),
        h("h3", {}, "还没有待办事务"), h("p", {}, "可从回答中加入办理清单。"),
        h("button", { type: "button", class: "text-button", onclick: () => show("chat") }, "返回对话")));
    panel.replaceChildren(toolbar("办理清单", "chat"), content);
    content.scrollTop = listScroll;
  }
  function renderDetail(task) {
    const list = h("ul", { class: "checklist handling-items" });
    for (const item of task.items) {
      const id = `saved-${task.service_id}-${item.id}`;
      const box = h("input", { type: "checkbox", id, "data-item-id": item.id });
      box.checked = task.checked.includes(item.id);
      box.addEventListener("change", () => {
        const result = store.toggle(task.service_id, item.id);
        if (!result.ok) { box.checked = task.checked.includes(item.id); message(result.message); }
      });
      list.append(h("li", {}, box, h("label", { for: id }, item.text)));
    }
    const preparation = h("section", { class: "handling-section" },
      h("div", { class: "handling-section-title" }, h("h3", {}, "准备项"), h("span", {}, preparationLabel(task))), list,
      task.preparationUnknown && task.items.length ? h("p", { class: "fineprint" }, "部分准备要求待核实，可查看官方依据。") : null);
    const ways = h("section", { class: "handling-section" }, h("h3", {}, "办理方式"),
      task.entryPoints.length ? h("p", { class: "fineprint" }, task.entryPoints.join(" · ")) : null);
    for (const step of task.steps) {
      const locations = step.place_ids.map((id) => task.places.find((p) => p.place_id === id)).filter(Boolean);
      ways.append(h("div", { class: "handling-step" },
        h("b", { class: "handling-mode" }, MODES[step.mode] || "办理说明"),
        step.condition ? h("p", { class: "handling-condition" }, `适用：${step.condition}`) : null,
        h("p", {}, step.instruction),
        locations.map((p) => h("div", { class: "handling-place" }, h("span", {}, p.name),
          hasPosition(p) ? h("span", { class: "handling-place-actions" },
            h("button", { type: "button", class: "text-button", onclick: () => onFocus(p) }, "查看地点"),
            h("button", { type: "button", class: "text-button", onclick: () => onGo(p) }, "带我去"))
            : h("small", {}, "暂无位置"))),
        step.place_ids.length && !locations.length ? h("p", { class: "fineprint" }, "暂无位置，请按办理说明确认地点。") : null));
    }
    const sources = h("details", { class: "handling-sources" }, h("summary", {}, "查看官方依据"),
      task.audience ? h("p", { class: "fineprint" }, `适用：${task.audience}`) : null,
      h("p", { class: "fineprint" }, `按 ${new Date(task.savedAt).toLocaleDateString("zh-CN")} 加入时的信息保存，不随新回答自动更新。`),
      (task.sourceNotes || []).map((note) => h("p", { class: "fineprint" }, note)),
      task.sources.length ? h("ul", {}, task.sources.map((s) => h("li", {}, h("a", { href: sourceUrl(s.url), target: "_blank", rel: "noopener noreferrer" }, s.title))))
        : h("p", { class: "fineprint" }, "官方链接暂未收录。"));
    panel.replaceChildren(toolbar(task.title, "list", task),
      h("div", { class: "handling-scroll" }, preparation, ways,
        task.notes.length ? h("section", { class: "handling-section handling-notes" }, h("h3", {}, "注意事项"), h("ul", {}, task.notes.map((n) => h("li", {}, n)))) : null, sources),
      h("div", { class: "handling-footer" }, h("button", { type: "button", class: "handling-primary", onclick: () => remove(task, true) }, "我已办完")));
  }
  function render() {
    if (view === "chat") return;
    const task = selected && store.get(selected);
    if (view === "detail" && task) renderDetail(task);
    else { view = "list"; selected = null; renderList(); }
  }
  function sync() {
    const count = store.list().length;
    entry.textContent = count ? `办理清单 · ${count}` : "办理清单";
    for (const p of previews) {
      if (!p.button.isConnected) { previews.delete(p); continue; }
      p.button.textContent = store.get(p.id) ? "已加入 · 查看清单" : "＋ 加入办理清单";
    }
    // Preserve scroll and keyboard focus when a checkbox update rebuilds the detail.
    const scroll = panel.querySelector(".handling-scroll")?.scrollTop || 0;
    const itemId = document.activeElement?.dataset.itemId;
    render();
    const content = panel.querySelector(".handling-scroll");
    if (content) content.scrollTop = scroll;
    if (itemId) [...panel.querySelectorAll("[data-item-id]")].find((e) => e.dataset.itemId === itemId)?.focus({ preventScroll: true });
  }
  store.subscribe(sync);
  entry.addEventListener("click", () => open());
  panel.closest(".chat").addEventListener("keydown", (e) => {
    if (view === "chat" || e.key !== "Escape") return;
    e.preventDefault();
    const menu = panel.querySelector(".handling-menu[open]");
    if (menu) { menu.open = false; menu.querySelector("summary").focus(); }
    else show(view === "detail" ? "list" : "chat");
  });
  sync();
  return {
    get active() { return view !== "chat"; },
    showChat() { if (view !== "chat") show("chat"); },
    preview(body) {
      const task = taskSnapshot(body, getPlaces());
      if (!task) return null;
      const button = h("button", { type: "button", class: "handling-add", onclick: () => {
        if (store.get(task.service_id)) { open(task.service_id); return; }
        // Rebuild at click time: public place loading may have completed after the answer.
        const snapshot = taskSnapshot(body, getPlaces());
        snapshot.checked = getLegacyTicks(snapshot);
        const result = store.add(snapshot);
        if (!result.ok) { message(result.message); return; }
        if (result.existing) open(task.service_id);
        else message("已加入办理清单");
      } }, store.get(task.service_id) ? "已加入 · 查看清单" : "＋ 加入办理清单");
      previews.add({ id: task.service_id, button });
      return h("section", { class: "card handling-preview-card", "aria-label": "办理清单" },
        h("p", { class: "fineprint" }, "保存材料与步骤，下次继续查看。"), button);
    },
  };
}
