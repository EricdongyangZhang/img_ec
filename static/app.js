// ===== T恤生图机器人 · 前端逻辑 =====
"use strict";

const $ = (id) => document.getElementById(id);

// ---------- 工具 ----------
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}
function fmtTime(ts) {
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
async function api(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
function postJSON(url, body) {
  return api(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}
function putJSON(url, body) {
  return api(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}

// ---------- 标签页 ----------
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    $("panel-" + tab.dataset.tab).classList.add("active");
  });
});

// ---------- 状态 ----------
let lastStatus = {};
async function pollStatus() {
  try {
    const s = await api("/api/status");
    lastStatus = s;
    const dot = $("statusDot");
    dot.className = "status-dot";
    let text = "未启动";
    if (s.starting) { dot.classList.add("starting"); text = "启动中…"; }
    else if (s.running) { dot.classList.add("running"); text = "运行中"; }
    else if (s.error) { dot.classList.add("error"); text = "错误"; }
    $("statusText").textContent = text;
    $("statusText").title = s.error || "";

    $("startBtn").disabled = s.running || s.starting;
    $("stopBtn").disabled = !s.running;
    $("stateBadge").textContent = s.running ? (s.state || "—") : "—";
  } catch (e) { /* 忽略瞬时错误 */ }
}

// ---------- 会话 ----------
let lastSeq = 0;
const chatEl = $("chat");

function addTextRow(role, text, ts) {
  const row = document.createElement("div");
  row.className = "msg-row " + role;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  const time = document.createElement("div");
  time.className = "ts";
  time.textContent = fmtTime(ts);
  bubble.appendChild(time);
  row.appendChild(bubble);
  chatEl.appendChild(row);
}
function addSysRow(text, ts) {
  const row = document.createElement("div");
  row.className = "msg-row system";
  const s = document.createElement("span");
  s.className = "sys-text";
  s.textContent = `${text} · ${fmtTime(ts)}`;
  row.appendChild(s);
  chatEl.appendChild(row);
}
function addImageRow(images, ts) {
  const row = document.createElement("div");
  row.className = "msg-row bot";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const thumbs = document.createElement("div");
  thumbs.className = "thumbs";
  images.forEach((rel) => {
    const img = document.createElement("img");
    img.src = "/media/" + rel.split("/").map(encodeURIComponent).join("/");
    img.loading = "lazy";
    img.addEventListener("click", () => openLightbox(img.src));
    thumbs.appendChild(img);
  });
  const time = document.createElement("div");
  time.className = "ts";
  time.textContent = fmtTime(ts);
  bubble.appendChild(thumbs);
  bubble.appendChild(time);
  row.appendChild(bubble);
  chatEl.appendChild(row);
}
function renderEvent(ev) {
  if (ev.role === "system" || ev.type === "system") addSysRow(ev.text || "", ev.ts);
  else if (ev.type === "images") addImageRow(ev.images || [], ev.ts);
  else addTextRow(ev.role, ev.text || "", ev.ts);
}
function scrollBottom() { chatEl.scrollTop = chatEl.scrollHeight; }

async function pollSession() {
  try {
    const data = await api("/api/session?since=" + lastSeq);
    // 服务端清屏后 seq 会归零：检测到回退则重绘全部
    if (data.seq < lastSeq) {
      chatEl.innerHTML = "";
      lastSeq = 0;
      const all = await api("/api/session?since=0");
      all.events.forEach(renderEvent);
      lastSeq = all.seq;
      scrollBottom();
      return;
    }
    if (data.events.length) {
      data.events.forEach(renderEvent);
      lastSeq = data.seq;
      scrollBottom();
    }
  } catch (e) { /* 忽略瞬时错误 */ }
}

async function sendSim() {
  const text = $("simInput").value.trim();
  if (!text) return;
  const r = await postJSON("/api/session/send", { text });
  if (r.ok) $("simInput").value = "";
  else alert(r.error || "发送失败");
}
$("simSend").addEventListener("click", sendSim);
$("simInput").addEventListener("keydown", (e) => { if (e.key === "Enter") sendSim(); });
$("clearSession").addEventListener("click", async () => {
  await postJSON("/api/session/clear", {});
  chatEl.innerHTML = "";
  lastSeq = 0;
});

// ---------- 图片灯箱 ----------
function openLightbox(src) {
  $("lightboxImg").src = src;
  $("lightbox").classList.add("show");
}
$("lightbox").addEventListener("click", () => $("lightbox").classList.remove("show"));

// ---------- 机器人启停 ----------
$("startBtn").addEventListener("click", async () => {
  const kind = $("channelSelect").value;
  const r = await postJSON("/api/bot/start", { kind });
  if (!r.ok) alert(r.error || "启动失败");
  pollStatus();
});
$("stopBtn").addEventListener("click", async () => {
  await postJSON("/api/bot/stop", {});
  pollStatus();
});

// ---------- 提示词 ----------
let templates = [];
let currentTplId = null;

function renderTplList() {
  const ul = $("tplUl");
  ul.innerHTML = "";
  templates.forEach((t) => {
    const li = document.createElement("li");
    if (t.id === currentTplId) li.classList.add("active");
    const name = document.createElement("span");
    name.textContent = t.name;
    li.appendChild(name);
    if (t.is_active) {
      const b = document.createElement("span");
      b.className = "badge-active";
      b.textContent = "● 当前";
      li.appendChild(b);
    }
    li.addEventListener("click", () => selectTpl(t.id));
    ul.appendChild(li);
  });
}
function selectTpl(id) {
  currentTplId = id;
  const t = templates.find((x) => x.id === id);
  if (!t) return;
  $("tplName").value = t.name;
  $("tplText").value = t.template;
  $("pvOut").textContent = "";
  renderTplList();
}
async function loadPrompts() {
  const data = await api("/api/prompts");
  templates = data.templates || [];
  if (!templates.find((t) => t.id === currentTplId)) {
    const active = templates.find((t) => t.is_active) || templates[0];
    currentTplId = active ? active.id : null;
  }
  renderTplList();
  if (currentTplId) selectTpl(currentTplId);
}
function tplMsg(text, cls) {
  const el = $("tplMsg");
  el.textContent = text;
  el.className = "msg " + (cls || "");
  setTimeout(() => { el.textContent = ""; el.className = "msg"; }, 2500);
}
$("tplAdd").addEventListener("click", async () => {
  const r = await postJSON("/api/prompts", { name: "新模板", template: "" });
  if (r.ok) { currentTplId = r.template.id; await loadPrompts(); }
});
$("tplSave").addEventListener("click", async () => {
  if (!currentTplId) return tplMsg("请先选择模板", "err");
  const r = await putJSON("/api/prompts/" + currentTplId, {
    name: $("tplName").value, template: $("tplText").value,
  });
  if (r.ok) { tplMsg("已保存", "ok"); await loadPrompts(); }
  else tplMsg(r.error || "保存失败", "err");
});
$("tplActivate").addEventListener("click", async () => {
  if (!currentTplId) return;
  await postJSON("/api/prompts/" + currentTplId + "/activate", {});
  tplMsg("已设为当前", "ok");
  await loadPrompts();
});
$("tplDelete").addEventListener("click", async () => {
  if (!currentTplId) return;
  if (templates.length <= 1) return tplMsg("至少保留一个模板", "warn");
  if (!confirm("确认删除该模板？")) return;
  await api("/api/prompts/" + currentTplId, { method: "DELETE" });
  currentTplId = null;
  await loadPrompts();
});
$("pvBtn").addEventListener("click", async () => {
  const r = await postJSON("/api/prompts/preview", {
    template: $("tplText").value,
    base_color: $("pvBase").value,
    user_desc: $("pvDesc").value,
  });
  $("pvOut").textContent = r.rendered || "";
});

// ---------- 配置 ----------
async function loadConfig() {
  const c = await api("/api/config");
  $("GLM_API_KEY").value = c.GLM_API_KEY || "";
  $("GLM_API_KEY").placeholder = c._has_key ? "已配置（留空保持不变）" : "未配置，请填写";
  $("GLM_BASE_URL").value = c.GLM_BASE_URL || "";
  $("GLM_MODEL").value = c.GLM_MODEL || "";
  $("IMAGE_SIZE").value = c.IMAGE_SIZE || "1280x1280";
  $("IMAGE_QUALITY").value = c.IMAGE_QUALITY || "hd";
  $("NUM_CANDIDATES").value = c.NUM_CANDIDATES || "3";
  $("WATERMARK_ENABLED").checked = String(c.WATERMARK_ENABLED).toLowerCase() === "true";
  $("LISTEN_CHAT").value = c.LISTEN_CHAT || "";
  $("OUTPUT_DIR").value = c.OUTPUT_DIR || "";
}
$("cfgSave").addEventListener("click", async () => {
  const body = {
    GLM_API_KEY: $("GLM_API_KEY").value.trim(),
    GLM_BASE_URL: $("GLM_BASE_URL").value.trim(),
    GLM_MODEL: $("GLM_MODEL").value.trim(),
    IMAGE_SIZE: $("IMAGE_SIZE").value,
    IMAGE_QUALITY: $("IMAGE_QUALITY").value,
    NUM_CANDIDATES: $("NUM_CANDIDATES").value,
    WATERMARK_ENABLED: $("WATERMARK_ENABLED").checked,
    LISTEN_CHAT: $("LISTEN_CHAT").value.trim(),
    OUTPUT_DIR: $("OUTPUT_DIR").value.trim(),
  };
  const r = await postJSON("/api/config", body);
  const el = $("cfgMsg");
  if (r.ok) {
    if (r.warning) { el.textContent = "已保存，但：" + r.warning; el.className = "msg warn"; }
    else { el.textContent = "已保存并生效"; el.className = "msg ok"; }
    await loadConfig();
    setTimeout(() => { el.textContent = ""; el.className = "msg"; }, 3000);
  } else { el.textContent = "保存失败"; el.className = "msg err"; }
});

// ---------- 启动 ----------
pollStatus();
pollSession();
loadPrompts();
loadConfig();
setInterval(pollSession, 1500);
setInterval(pollStatus, 2000);
