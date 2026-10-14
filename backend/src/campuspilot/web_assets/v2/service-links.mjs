// Official service destinations are supplied by the evidence boundary, never parsed
// from generated answer prose. Validate again before making them clickable.
export const SERVICE_LINK_ACTIONS = {
  online: "打开办理入口",
  platform: "打开办事平台",
  guide: "查看办事指南",
};

const SECRET_KEYS = new Set(["token", "access_token", "refresh_token", "id_token", "ticket", "password", "passwd", "cookie", "session", "sessionid", "jsessionid", "api_key", "apikey", "key", "username", "user_id", "userid", "student_id", "studentid", "account", "authorization", "auth_token", "code", "credential"]);
const REDIRECT_KEYS = new Set(["service", "redirect", "redirect_uri", "redirect_url", "returnurl", "return_url", "callback", "callback_url", "url", "target", "next"]);
const decode = (value) => {
  for (let i = 0; i < 3; i++) {
    const next = decodeURIComponent(value);
    if (next === value) break;
    value = next;
  }
  return value;
};

export function safeServiceUrl(value, depth = 0) {
  if (typeof value !== "string" || !value || value.length > 2048 || depth > 3) return null;
  try {
    const decoded = decode(value);
    if (/[\s\u0000-\u001f\u007f\\]/.test(decoded)) return null;
    const url = new URL(value);
    const official = url.hostname === "cdut.edu.cn" || url.hostname.endsWith(".cdut.edu.cn");
    if (url.protocol !== "https:" || !official || url.username || url.password || url.hash || (url.port && url.port !== "443")) return null;
    const path = decode(url.pathname);
    if (/[*{}]/.test(path) || /;jsessionid/i.test(path)) return null;
    for (const [rawKey, rawTarget] of url.searchParams) {
      const key = decode(rawKey).toLowerCase();
      if (SECRET_KEYS.has(key)) return null;
      if (REDIRECT_KEYS.has(key)) {
        const target = decode(rawTarget);
        if (!target) return null;
        // Resolve relative returns as well, so their own credential parameters cannot hide.
        const returnUrl = new URL(target, url).href;
        if (!safeServiceUrl(returnUrl, depth + 1)) return null;
      }
    }
    return url.href;
  } catch { return null; }
}

export function serviceLinkHints(link) {
  const hints = [];
  if (link.requires_login === true) hints.push("需学校账号登录");
  else if (link.requires_login == null) hints.push("登录条件未核实");
  if (link.network_requirement === "campus_or_vpn") hints.push("校外可能需校园网或 VPN");
  else hints.push("网络条件未核实");
  return hints;
}

export function normalizeServiceLinks(body) {
  if (!body || !["success", "limited"].includes(body.result_status || "success") || !Array.isArray(body.service_links)) return [];
  const seen = new Set();
  return body.service_links.flatMap((link) => {
    if (!link || typeof link !== "object" || !Object.hasOwn(SERVICE_LINK_ACTIONS, link.kind)) return [];
    const url = safeServiceUrl(link.url);
    const sourceUrl = link.source_url == null ? null : safeServiceUrl(link.source_url);
    if (!url || (link.source_url != null && !sourceUrl)) return [];
    const key = `${link.kind}:${url}`;
    if (seen.has(key)) return [];
    seen.add(key);
    return [{
      ...link,
      url,
      source_url: sourceUrl,
      title: typeof link.title === "string" && link.title.trim() ? link.title : "官方办事链接",
      source_title: typeof link.source_title === "string" ? link.source_title : "官方材料",
      action_label: SERVICE_LINK_ACTIONS[link.kind],
      hints: serviceLinkHints(link),
    }];
  }).slice(0, 8);
}
