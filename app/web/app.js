// Parlo window. Talks to Python through window.pywebview.api; Python calls window.onBark(kind, data).
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const S = { page: "home", note: null, saveTimer: null, range: null, capture: null };
let API;

// ---------- startup ----------
function boot() {
  if (API) return;
  API = window.pywebview ? window.pywebview.api : demoApi();
  hydrateIcons();
  API.ui_ready().then(async (st) => {
    Object.assign(S, st); renderAll(); go(location.hash.slice(1) || "home");
    const m = await API.meeting_state(); if (m) { S.meeting = { ...m, state: "recording" }; renderMeeting(); }
    if (!S.settings.onboarded) startTour();
  });
}
if (window.pywebview && window.pywebview.api) boot(); else window.addEventListener("pywebviewready", boot);
if (location.search.includes("demo")) boot(); // index.html?demo in a normal browser, for design work

window.onBark = (kind, data) => {
  if (kind === "status") { S.status = data; renderStatus(); }
  else if (kind === "models") { S.models = data; renderModels(); }
  else if (kind === "history") { S.history = data.items; S.stats = data.stats; renderHome(); renderHistory(); }
  else if (kind === "note_insert") { applyTokens(data); }
  else if (kind === "level") {
    const v = Math.min(1, data);
    const r = $("#noteMic .ring"); if (r && S.status?.target === "note") r.style.transform = `scale(${0.6 + v * 0.9})`;
    const tm = $("#tourMeter"); if (tm) tm.style.width = `${Math.min(100, Math.sqrt(v) * 160)}%`;
    $$("#heroOrb .wave i").forEach((b, i) => { b.style.height = `${8 + v * 30 * (0.55 + 0.45 * Math.abs(Math.sin(Date.now() / 140 + i * 1.7)))}px`; });
  }
  else if (kind === "toast") { toast(data); }
  else if (kind === "settings") { S.settings = data; applyTheme(); renderSettings(); renderHome(); renderModes(); }
  else if (kind === "meeting") { onMeeting(data); }
  else if (kind === "notes") { S.notes = data; renderNotesList(); }
  else if (kind === "llms") { S.llms = data; renderLlms(); }
  else if (kind === "tts") { S.tts = data; renderRead(); }
  else if (kind === "reading") { S.reading = data; renderRead(); }
  else if (kind === "live") { const l = $("#liveNote"); l.textContent = data; l.hidden = false; }
  else if (kind === "navigate") { go(data); if (data === "notes" && !S.note) newNote(); }
};

function renderAll() {
  applyTheme(); renderStatus(); renderHome(); renderHistory(); renderModels(); renderSettings(); renderNotesList(); renderModes(); renderRead();
}

// ---------- navigation ----------
function go(page) {
  S.page = page;
  $$(".nav").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  $$(".page").forEach((p) => p.classList.toggle("active", p.id === "page-" + page));
  moveIndicator();
  stagger($("#page-" + page));
  if (page === "models") refreshEngineMemory();
}

// ---------- motion ----------
const navIndicator = document.createElement("div");
navIndicator.className = "nav-indicator";
$("nav").prepend(navIndicator);
function moveIndicator() {
  const b = $(".nav.active");
  if (!b) return;
  navIndicator.style.transform = `translateY(${b.offsetTop}px)`;
  navIndicator.style.height = b.offsetHeight + "px";
}
window.addEventListener("resize", moveIndicator);
// cards and rows rise in one after another when a page opens
function stagger(root) {
  if (!root) return;
  $$(".hero, .stat, .item, .model, .mode-card, .group, .card, .nitem", root).slice(0, 24).forEach((el, i) => {
    el.classList.remove("enter"); void el.offsetWidth;
    el.style.setProperty("--i", Math.min(i, 14)); el.classList.add("enter");
  });
}
// a soft glow follows the pointer across cards
document.addEventListener("pointermove", (e) => {
  const card = e.target.closest(".stat, .item, .model, .mode-card, .card, .hero");
  if (!card) return;
  const r = card.getBoundingClientRect();
  card.style.setProperty("--mx", `${e.clientX - r.left}px`);
  card.style.setProperty("--my", `${e.clientY - r.top}px`);
});
// numbers count up to their new value
function countTo(el, value, format = (v) => Math.round(v).toLocaleString()) {
  const from = parseFloat(el.dataset.v || "0"), start = performance.now(), dur = 700;
  el.dataset.v = value;
  if (from === value || matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = format(value); return; }
  const step = (t) => {
    const k = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = format(from + (value - from) * e);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}
// copy buttons flip to a tick for a moment
function flashDone(btn) {
  if (!btn) return;
  const old = btn.innerHTML; btn.classList.add("done"); btn.innerHTML = icon("check");
  setTimeout(() => { btn.classList.remove("done"); btn.innerHTML = old; }, 1200);
}
$$(".nav").forEach((b) => (b.onclick = () => go(b.dataset.page)));
document.addEventListener("click", (e) => { const g = e.target.closest("[data-goto]"); if (g) go(g.dataset.goto); });
$("#engineCard").onclick = () => go("models");

// ---------- helpers ----------
const KEYNAMES = { ctrl: "Ctrl", win: "⊞ Win", alt: "Alt", shift: "Shift", space: "Space", escape: "Esc", enter: "Enter" };
const keysHtml = (combo) => (combo || "").split("+").filter(Boolean).map((k) => `<kbd>${esc(KEYNAMES[k] || k.toUpperCase())}</kbd>`).join("");
function toast(msg, ic = "info") {
  const t = document.createElement("div"); t.className = "toast";
  t.innerHTML = icon(ic) + `<span>${esc(msg)}</span>`;
  $("#toasts").append(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 260); }, 3800);
}
function when(t) {
  const d = new Date(t * 1000), now = new Date();
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === now.toDateString()) return time;
  return d.toLocaleDateString([], { day: "numeric", month: "short" }) + ", " + time;
}
function modal(title, bodyHtml, buttons) {
  $("#modalTitle").textContent = title; $("#modalBody").innerHTML = bodyHtml; $("#modalFoot").innerHTML = "";
  $("#modalBody").style.whiteSpace = /^\s*</.test(bodyHtml) ? "normal" : ""; // markup bodies: no pre-wrap gaps
  for (const [label, cls, fn] of buttons) {
    const b = document.createElement("button"); b.className = "btn " + cls; b.innerHTML = label;
    b.onclick = () => { if (fn() !== false) closeModal(); }; $("#modalFoot").append(b);
  }
  hydrateIcons($("#modal")); $("#modal").hidden = false;
}
const closeModal = () => ($("#modal").hidden = true);
$("#modalClose").onclick = closeModal;
$("#modal").onclick = (e) => { if (e.target.id === "modal") closeModal(); };

function applyTheme() {
  const t = S.settings.theme;
  const dark = t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => S.settings && applyTheme());

// ---------- status ----------
function renderStatus() {
  const st = S.status || {};
  const recording = st.state === "recording", busy = st.state === "transcribing";
  const dotCls = recording ? "recording" : st.engine;
  $("#engineDot").className = "dot " + dotCls;
  $("#engineCard").className = "engine-card " + (recording ? "recording" : st.engine === "loading" ? "loading shimmer" : "");
  $("#engineName").textContent = st.model || "No model";
  if (!(recording && st.target === "note")) $("#liveNote").hidden = true;
  $("#engineSub").textContent = recording ? "Listening…" : busy ? "Transcribing…" : st.state === "polishing" ? "Polishing with AI…" :
    { ready: "Ready · runs on this PC", loading: "Loading model…", missing: "Download a model to start", error: "Problem loading — click for details" }[st.engine] || "";
  $("#heroOrb").classList.toggle("live", recording && st.target === "insert");
  $("#heroOrb").classList.toggle("ready", st.engine === "ready" && st.state === "idle"); // breathe only when it can be used
  const combo = (S.settings?.dictate_hotkey || "").split("+").filter(Boolean).map((k) => KEYNAMES[k] || k.toUpperCase()).join(" + ");
  $("#heroOrb").title = st.engine === "ready" ? `Press ${combo} in any app to dictate` : "";
  const fab = $("#noteMic");
  const noteLive = st.target === "note" && (recording || busy);
  fab.classList.toggle("live", noteLive && recording);
  fab.classList.toggle("busy", noteLive && busy);
  fab.querySelector(".mic-label").textContent = noteLive && recording ? "Stop" : noteLive && busy ? "Writing…" : "Dictate";
  if (!(noteLive && recording)) fab.querySelector(".ring").style.transform = "scale(0)";
}

// ---------- home ----------
function renderHome() {
  const s = S.settings, st = S.stats;
  $("#heroKeys").innerHTML = keysHtml(s.dictate_hotkey);
  $("#heroMode").textContent = {
    automatic: "Tap to start and tap again to stop, or hold while you talk. Your words appear wherever you're typing.",
    push_to_talk: "Hold while you talk and let go to insert your words wherever you're typing.",
    toggle: "Tap to start, tap again to stop. Your words appear wherever you're typing.",
  }[s.activation];
  countTo($("#stToday"), st.today_words);
  countTo($("#stTotal"), st.total_words);
  countTo($("#stSaved"), st.saved_min, (v) => (st.saved_min >= 60 ? (v / 60).toFixed(1) + " h" : Math.round(v) + " min"));
  countTo($("#stCount"), st.count);
  $("#modeSel").innerHTML = s.modes.map((m) => `<option value="${esc(m.id)}" ${m.id === s.active_mode ? "selected" : ""}>${esc(m.name)}</option>`).join("");
  const recent = S.history.slice(0, 5);
  $("#recentList").innerHTML = recent.length ? recent.map(itemHtml).join("") :
    `<div class="empty">Nothing yet. Press ${keysHtml(s.dictate_hotkey)} in any app and say something.</div>`;
  hydrateIcons($("#recentList"));
  renderActivity();
}
function itemHtml(e) {
  const words = e.text.split(/\s+/).filter(Boolean).length;
  return `<div class="item" data-t="${e.t}"><div class="text"><div class="t">${esc(e.text)}</div>
    <div class="meta"><span>${when(e.t)}</span><span>${words} words</span><span>${e.secs}s audio</span>${e.app && e.app !== "file" ? `<span>${esc(appName(e.app))}</span>` : ""}${e.mode ? `<span class="badge" title="${esc("Before AI: " + (e.raw || ""))}">${icon("sparkles")}${esc(e.mode)}</span>` : ""}</div></div>
    <div class="tools"><button class="tool" data-act="copy" title="Copy"><span data-icon="copy"></span></button>
    <button class="tool" data-act="speak" title="Read aloud"><span data-icon="speaker"></span></button>
    <button class="tool danger" data-act="del" title="Delete"><span data-icon="trash"></span></button></div></div>`;
}
document.addEventListener("click", async (e) => {
  const btn = e.target.closest(".item .tool"); if (!btn) return;
  const t = parseFloat(btn.closest(".item").dataset.t);
  const entry = S.history.find((h) => h.t === t); if (!entry) return;
  if (btn.dataset.act === "copy") { await API.copy_text(entry.text); flashDone(btn); }
  if (btn.dataset.act === "speak") API.speak(entry.text);
  if (btn.dataset.act === "del") { S.stats = await API.delete_history(t); S.history = S.history.filter((h) => h.t !== t); renderHome(); renderHistory(); }
});
$("#fileBtn").onclick = async () => {
  modal("Transcribe a file", `<div style="display:flex;gap:10px;align-items:center"><span class="spinner"></span> Choose a file… long recordings take a while.</div>`, []);
  const r = await API.pick_and_transcribe();
  if (!r) return closeModal();
  if (r.error) return modal("Could not transcribe", esc(r.error), [["OK", "primary", () => {}]]);
  modal(`${r.name} · ${Math.round(r.secs / 60)} min`, esc(r.text || "(no speech found)"), [
    [icon("copy") + "Copy", "ghost", () => { API.copy_text(r.text); toast("Copied"); }],
    [icon("note") + "Save as note", "primary", async () => { await newNote(r.name, `<p>${esc(r.text)}</p>`); go("notes"); }],
  ]);
};

// ---------- history ----------
function renderHistory() {
  const q = $("#histSearch").value.trim().toLowerCase();
  const items = S.history.filter((e) => !q || e.text.toLowerCase().includes(q));
  $("#histList").innerHTML = items.length ? items.map(itemHtml).join("") : `<div class="empty">${q ? "No matches." : "Your dictations will appear here."}</div>`;
  hydrateIcons($("#histList"));
}
$("#histSearch").oninput = renderHistory;
$("#clearHist").onclick = () => modal("Clear history?", "This deletes every saved dictation.", [
  ["Cancel", "ghost", () => {}],
  ["Delete all", "primary", async () => { S.stats = await API.clear_history(); S.history = []; renderHome(); renderHistory(); }],
]);

// ---------- read aloud ----------
const LANG_NAMES = { a: "US English", b: "UK English", e: "Spanish", f: "French", i: "Italian", p: "Portuguese" };
const voiceLabel = (id) => { const [p, n] = id.split("_"); return `${n[0].toUpperCase() + n.slice(1)} · ${LANG_NAMES[p[0]] || ""} · ${p[1] === "m" ? "male" : "female"}`; };
function renderRead() {
  const s = S.settings, tts = S.tts || { installed: false, voices: [] };
  if (!s) return;
  const natural = s.tts_engine === "kokoro";
  $$("#ttsEngine button").forEach((b) => b.classList.toggle("on", b.dataset.v === s.tts_engine));
  $("#kokoroGet").hidden = !(natural && !tts.installed);
  const dl = tts.download;
  $("#kokoroFoot").innerHTML = dl ? `<div class="progress"><i style="width:${Math.round(dl.progress * 100)}%"></i></div><span class="muted small">${Math.round(dl.progress * 100)}%</span>`
    : `<button class="btn primary sm" id="getKokoro">${icon("download")}Download natural voices (${tts.size_mb || 116} MB)</button>`;
  const getBtn = $("#getKokoro"); if (getBtn) getBtn.onclick = () => API.download_model("kokoro");
  const useNatural = natural && tts.installed;
  $("#ttsNote").textContent = useNatural ? "Lifelike voices, running on this PC." : natural ? "Download once to use them." : "The voices built into Windows.";
  $("#voiceSel").innerHTML = useNatural
    ? tts.voices.map((v) => `<option value="${v}" ${v === s.kokoro_voice ? "selected" : ""}>${esc(voiceLabel(v))}</option>`).join("")
    : (S.voices || []).map((v) => `<option ${v === s.voice ? "selected" : ""}>${esc(v)}</option>`).join("");
  $("#tryVoice").hidden = !useNatural;
  $("#ttsPlay").innerHTML = icon(S.reading ? "stop" : "play") + (S.reading ? "Stop" : "Speak");
}
$("#ttsEngine").onclick = (e) => { const b = e.target.closest("button"); if (b) saveSetting("tts_engine", b.dataset.v); };
$("#ttsPlay").onclick = () => (S.reading ? API.stop_speaking() : API.speak($("#ttsText").value));
$("#ttsStop").onclick = () => API.stop_speaking();
$("#tryVoice").onclick = () => API.try_voice($("#voiceSel").value);
$("#voiceSel").onchange = (e) => saveSetting(S.settings.tts_engine === "kokoro" && (S.tts || {}).installed ? "kokoro_voice" : "voice", e.target.value);
$("#rateSel").onchange = (e) => saveSetting("rate", parseInt(e.target.value));

// ---------- your own models ----------
function hfDialog(kind) {
  const isLlm = kind === "llm";
  modal(isLlm ? "Add an AI model from Hugging Face" : "Add a Whisper model from Hugging Face",
    `<p class="muted small" style="margin:0 0 10px">${isLlm
      ? "Paste a model link or name, e.g. <code>Qwen/Qwen3-8B-GGUF</code>. Pick a GGUF chat model; Q4_K_M files are a good balance of size and quality."
      : "Paste a faster-whisper model link or name, e.g. <code>Systran/faster-distil-whisper-large-v3</code>."}</p>
     <div style="display:flex;gap:8px"><input type="text" id="hfRepo" placeholder="Org/Model-name" spellcheck="false"><button class="btn sm" id="hfLook">Look up</button></div>
     <div id="hfOut"></div>`, [["Cancel", "ghost", () => {}]]);
  const look = async () => {
    const out = $("#hfOut"); out.innerHTML = `<p class="muted small"><span class="spinner"></span> Looking it up…</p>`;
    const r = await API.inspect_hf($("#hfRepo").value, kind);
    if (!r.ok) { out.innerHTML = `<p class="warn">${esc(r.error)}</p>`; return; }
    if (isLlm) {
      out.innerHTML = `<div class="hf-files">${r.choices.map((c, i) => `<label><input type="radio" name="hff" value="${esc(c.file)}" ${/q4_k_m/i.test(c.file) || (i === 0 && !r.choices.some((x) => /q4_k_m/i.test(x.file))) ? "checked" : ""}>
        <span class="grow">${esc(c.file)}</span><span class="muted small">${c.mb >= 1024 ? (c.mb / 1024).toFixed(1) + " GB" : c.mb + " MB"}</span></label>`).join("")}</div>
        <p class="muted small">Licence: ${esc(r.license)}. Needs roughly the file size plus 20% of free memory.</p>`;
    } else {
      out.innerHTML = `<p class="small">${esc(r.repo)} · ${r.mb >= 1024 ? (r.mb / 1024).toFixed(1) + " GB" : r.mb + " MB"} · licence ${esc(r.license)}</p>`;
    }
    const foot = $("#modalFoot"); foot.innerHTML = "";
    const add = document.createElement("button"); add.className = "btn primary"; add.innerHTML = icon("download") + "Add and download";
    add.onclick = async () => {
      const res = isLlm ? await API.add_custom_llm(r, $("input[name=hff]:checked").value) : await API.add_custom_whisper(r);
      closeModal(); toast(res.warn || "Downloading… it will appear in the list.");
    };
    foot.append(add);
  };
  $("#hfLook").onclick = look;
  $("#hfRepo").onkeydown = (e) => { if (e.key === "Enter") look(); };
  setTimeout(() => $("#hfRepo").focus(), 50);
}
$("#addLlmHf").onclick = () => hfDialog("llm");
$("#addWhisper").onclick = () => hfDialog("whisper");
$("#addLlmFile").onclick = async () => {
  const r = await API.add_custom_llm_file(); if (!r) return;
  if (r.error) return toast(r.error);
  toast(r.warn || "Added. Press 'Use this model' to switch to it.");
};

// ---------- models ----------
const bars = (n) => `<span class="bars">${[1, 2, 3, 4, 5].map((i) => `<i class="${i <= n ? "f" : ""}"></i>`).join("")}</span>`;
function renderModels() {
  $("#modelGrid").innerHTML = S.models.map((m) => {
    const dl = m.download;
    let chip = m.active ? `<span class="chip on">${S.status.engine === "loading" ? "Loading…" : "In use"}</span>` : m.installed ? `<span class="chip ok">Downloaded</span>` : `<span class="chip">${m.size_mb >= 1000 ? (m.size_mb / 1024).toFixed(1) + " GB" : m.size_mb + " MB"}</span>`;
    let foot;
    if (dl) foot = `<div class="progress"><i style="width:${Math.round(dl.progress * 100)}%"></i></div><span class="muted small">${Math.round(dl.progress * 100)}%</span><button class="btn ghost sm" data-m="cancel">Cancel</button>`;
    else if (m.active) foot = `<button class="btn sm" disabled>${icon("check")}Active</button>`;
    else if (m.installed) foot = `<button class="btn primary sm" data-m="use" data-id="${m.id}">Use this model</button><button class="tool danger" data-m="delete" data-id="${m.id}" title="Delete download">${icon("trash")}</button>`;
    else foot = `<button class="btn sm" data-m="download" data-id="${m.id}">${icon("download")}Download</button>`;
    return `<div class="model ${m.active ? "active" : ""}">
      <div class="model-head"><div class="model-ico fam-${m.family}">${icon(m.family === "Whisper" ? "globe" : "mic")}</div>
        <div><b>${esc(m.name)}</b><small>${m.family} · ${esc(m.license)}</small></div>${chip}</div>
      <p>${esc(m.blurb)}</p>
      ${m.accuracy ? `<div class="meters"><span>Accuracy</span>${bars(m.accuracy)}<span>Speed</span>${bars(m.speed)}</div>` : `<span class="chip mine" style="margin:0;align-self:flex-start">Your model · untested</span>`}
      <div class="tags"><span class="tag">${icon(m.languages === "English" ? "type" : "globe")}${esc(m.languages)}</span>
        <span class="tag">${icon("memory")}~${m.ram_gb} GB RAM</span>
        <span class="tag">${icon("download")}${m.size_mb >= 1000 ? (m.size_mb / 1024).toFixed(1) + " GB" : m.size_mb + " MB"}</span></div>
      <div class="model-foot">${foot}</div></div>`;
  }).join("");
  if (S.status.engine === "error") {
    $("#modelGrid").insertAdjacentHTML("afterbegin", `<div class="card" style="grid-column:1/-1;border-color:var(--red)"><b>The model could not load.</b><div class="muted small">${esc(S.status.message)}</div></div>`);
  }
}
$("#modelGrid").onclick = async (e) => {
  const b = e.target.closest("[data-m]"); if (!b) return;
  const id = b.dataset.id;
  if (b.dataset.m === "download") { if (!(await API.download_model(id))) toast("Another download is still running"); }
  if (b.dataset.m === "cancel") API.cancel_download();
  if (b.dataset.m === "use") { const warn = await API.set_model(id); toast(warn || "Switching model…"); }
  if (b.dataset.m === "delete") modal("Delete this model?", "You can download it again later.", [
    ["Cancel", "ghost", () => {}], ["Delete", "primary", () => { API.delete_model(id); }]]);
};
async function refreshEngineMemory() {
  const mb = await API.engine_memory();
  if (mb && S.status.engine === "ready") $("#engineSub").textContent = `Ready · using ${(mb / 1024).toFixed(1)} GB RAM`;
}

// ---------- settings ----------
async function saveSetting(key, value) {
  S.settings = await API.save_settings({ [key]: value });
  if (key === "theme") applyTheme();
  renderSettings(); renderHome();
}
function renderSettings() {
  const s = S.settings;
  $("#dictKeys").innerHTML = keysHtml(s.dictate_hotkey);
  $("#readKeys").innerHTML = $("#readKeys2").innerHTML = keysHtml(s.read_hotkey);
  $$(".seg[data-setting]").forEach((seg) => $$("button", seg).forEach((b) => b.classList.toggle("on", b.dataset.v === s[seg.dataset.setting])));
  $$("input[type=checkbox][data-setting]").forEach((c) => (c.checked = !!s[c.dataset.setting]));
  $("select[data-setting=action]").value = s.action;
  $("#micSel").innerHTML = `<option value="">System default</option>` + S.mics.map((m) => `<option ${m === s.microphone ? "selected" : ""}>${esc(m)}</option>`).join("");
  renderRead();
  $("#rateSel").value = s.rate;
  if (document.activeElement !== $("#replText")) $("#replText").value = s.replacements;
  renderSync(); renderExtraSettings();
}
$$(".seg[data-setting]").forEach((seg) => (seg.onclick = (e) => { const b = e.target.closest("button"); if (b) saveSetting(seg.dataset.setting, b.dataset.v); }));
$$("input[type=checkbox][data-setting]").forEach((c) => (c.onchange = () => saveSetting(c.dataset.setting, c.checked)));
$("select[data-setting=action]").onchange = (e) => saveSetting("action", e.target.value);
$("#micSel").onchange = (e) => saveSetting("microphone", e.target.value || null);
$("#saveRepl").onclick = async () => { await saveSetting("replacements", $("#replText").value); toast("Replacements saved"); };

// shortcut capture: collect every key held at once; finish when all are released
const KEYMAP = { Control: "ctrl", Alt: "alt", Shift: "shift", Meta: "win", OS: "win", " ": "space", AltGraph: "alt" };
$$("[data-capture]").forEach((b) => (b.onclick = () => startCapture(b.dataset.capture)));
function startCapture(key) {
  S.capture = { key, held: new Set(), seen: [] };
  $("#captureKeys").innerHTML = "<kbd>…</kbd>"; $("#capture").hidden = false;
  API.capture_shortcut(true);
}
function endCapture(save) {
  const c = S.capture; S.capture = null; $("#capture").hidden = true; API.capture_shortcut(false);
  if (!save || !c.seen.length) return;
  if (c.key.startsWith("mode:")) { // a mode's own shortcut
    const m = S.settings.modes.find((x) => x.id === c.key.slice(5));
    if (m) { m.hotkey = c.seen.join("+"); saveModes(); }
  } else saveSetting(c.key, c.seen.join("+"));
}

// ---------- AI modes ----------
const MODE_ICONS = { plain: "mic", clean: "sparkles", email: "mail", bullets: "list", formal: "briefcase" };
function renderModes() {
  const s = S.settings, prov = S.providers || {};
  if (!s) return;
  if (document.activeElement?.closest?.("#page-modes .card.group") == null) {
    $("#provSel").innerHTML = Object.entries(prov).map(([id, p]) => `<option value="${id}" ${id === s.ai_provider ? "selected" : ""}>${esc(p.name)}</option>`).join("");
    $("#aiModel").value = s.ai_model; $("#aiBase").value = s.ai_base_url;
    $("#aiKey").value = ""; providerChanged();
  }
  $("#modeList").innerHTML = s.modes.map((m) => `
    <div class="mode-card ${m.id === s.active_mode ? "default" : ""}" data-id="${esc(m.id)}">
      <div class="mode-top"><div class="model-ico">${icon(MODE_ICONS[m.id] || m.icon || "sparkles")}</div>
        <input class="mode-name" value="${esc(m.name)}" ${m.id === "plain" ? "disabled" : ""}>
        ${m.id === s.active_mode ? `<span class="chip on">Default</span>` : `<button class="btn ghost sm" data-mact="default">Make default</button>`}</div>
      ${m.id === "plain" ? `<p class="muted small" style="margin:0">Inserts exactly what you said, with no AI. Works fully offline.</p>`
        : `<textarea class="mode-instr" placeholder="Tell the AI how to rewrite your dictation…">${esc(m.instructions)}</textarea>`}
      <div class="mode-foot"><span class="muted small">Shortcut</span><span class="keys">${m.hotkey ? keysHtml(m.hotkey) : `<span class="muted small">none</span>`}</span>
        <button class="btn ghost sm" data-mact="key">${m.hotkey ? "Change" : "Add"}</button>
        ${m.hotkey ? `<button class="btn ghost sm" data-mact="nokey">Remove</button>` : ""}
        <span class="grow"></span>${m.id === "plain" ? "" : `<button class="tool danger" data-mact="del" title="Delete mode">${icon("trash")}</button>`}</div>
      ${appChips(m)}
    </div>`).join("");
}
function renderLlms() {
  const list = S.llms || [], local = $("#provSel").value === "local";
  $("#llmBox").hidden = !local;
  if (!local) return;
  $("#llmGrid").innerHTML = list.map((m) => {
    const dl = m.download, size = m.size_mb >= 1000 ? (m.size_mb / 1024).toFixed(1) + " GB" : m.size_mb + " MB";
    let foot;
    if (dl) foot = `<div class="progress"><i style="width:${Math.round(dl.progress * 100)}%"></i></div><span class="muted small">${Math.round(dl.progress * 100)}%</span><button class="btn ghost sm" data-l="cancel">Cancel</button>`;
    else if (m.active && m.installed) foot = `<button class="btn sm" disabled>${icon("check")}In use</button>`;
    else if (m.installed) foot = `<button class="btn primary sm" data-l="use" data-id="${m.id}">Use this model</button><button class="tool danger" data-l="delete" data-id="${m.id}" title="Delete download">${icon("trash")}</button>`;
    else foot = `<button class="btn ${m.id === "qwen2.5-1.5b" ? "primary" : ""} sm" data-l="download" data-id="${m.id}">${icon("download")}Download (${size})</button>`;
    const chip = m.loaded ? `<span class="chip ok">Loaded</span>` : m.active && m.installed ? `<span class="chip on">Selected</span>` : m.installed ? `<span class="chip ok">Downloaded</span>` : "";
    return `<div class="model ${m.active && m.installed ? "active" : ""}">
      <div class="model-head"><div class="model-ico fam-Parakeet">${icon("sparkles")}</div>
        <div><b>${esc(m.name)}</b><small>${esc(m.family)} · ${esc(m.license)} · free</small></div>${chip}</div>
      <p>${esc(m.blurb)}</p>
      ${m.accuracy ? `<div class="meters"><span>Quality</span>${bars(m.accuracy)}<span>Speed</span>${bars(m.speed)}</div>` : `<span class="chip mine" style="margin:0;align-self:flex-start">Your model · untested</span>`}
      <div class="tags"><span class="tag">${icon("bolt")}${esc(m.secs)} per clean-up</span><span class="tag">${icon("memory")}~${m.ram_gb} GB RAM</span><span class="tag">${icon("download")}${size}</span></div>
      <div class="model-foot">${foot}</div></div>`;
  }).join("");
}
$("#llmGrid").onclick = async (e) => {
  const b = e.target.closest("[data-l]"); if (!b) return;
  const id = b.dataset.id;
  if (b.dataset.l === "download") { if (!(await API.download_model(id))) toast("Another download is still running"); }
  if (b.dataset.l === "cancel") API.cancel_download();
  if (b.dataset.l === "use") { const r = await API.set_llm(id); S.settings = r.settings; toast(r.warn || "AI model selected"); }
  const m = (S.llms || []).find((x) => x.id === id);
  if (b.dataset.l === "delete") modal(m && m.local_file ? "Remove this model from Parlo?" : "Delete this AI model?",
    m && m.local_file ? "Your .gguf file stays where it is; Parlo just stops listing it." : "You can download it again later.", [
    ["Cancel", "ghost", () => {}], ["Delete", "primary", () => { API.delete_llm(id); }]]);
};
function providerChanged() {
  const id = $("#provSel").value, p = (S.providers || {})[id] || {};
  $("#provNote").textContent = p.note || "";
  $("#keyRow").hidden = id === "ollama" || id === "local";
  $("#modelRow").hidden = id === "local";
  $("#saveAi").hidden = id === "local" && S.settings.ai_provider === "local";
  $("#baseRow").hidden = !(id === "custom" || id === "ollama");
  renderLlms();
  $("#aiModel").placeholder = p.model || "model name";
  $("#aiBase").placeholder = p.base || "https://…/v1";
  $("#aiKey").placeholder = S.settings.ai_key_set && id === S.settings.ai_provider ? "Saved (type to replace)" : "Paste your API key";
  $("#keyLink").hidden = !p.key_url;
}
$("#provSel").onchange = async () => {
  if ($("#provSel").value === "local") S.settings = await API.save_ai("local", "", "", null); // nothing else to fill in
  providerChanged();
};
$("#keyLink").onclick = (e) => { e.preventDefault(); API.open_key_page($("#provSel").value); };
async function saveAiConfig() {
  const key = $("#aiKey").value.trim();
  S.settings = await API.save_ai($("#provSel").value, $("#aiModel").value, $("#aiBase").value, key ? key : null);
  $("#aiKey").value = ""; providerChanged();
}
$("#saveAi").onclick = async () => { await saveAiConfig(); toast("AI service saved"); };
$("#testAi").onclick = async () => {
  await saveAiConfig();
  const box = $("#aiResult"); box.hidden = false; box.className = "ai-result"; box.innerHTML = `<span class="spinner"></span> Asking the AI…`;
  const r = await API.test_ai();
  if (r.ok) box.innerHTML = `It works (${r.secs}s).<b>You said</b>${esc(r.before)}<b>Clean up mode gives</b>${esc(r.after)}`;
  else { box.className = "ai-result bad"; box.textContent = r.error; }
};
async function saveModes() { S.settings = await API.save_modes(S.settings.modes, S.settings.active_mode); renderModes(); renderHome(); }
$("#modeList").addEventListener("input", (e) => {
  const card = e.target.closest(".mode-card"), m = S.settings.modes.find((x) => x.id === card.dataset.id);
  if (e.target.classList.contains("mode-name")) m.name = e.target.value;
  if (e.target.classList.contains("mode-instr")) m.instructions = e.target.value;
  clearTimeout(S.modeTimer); S.modeTimer = setTimeout(async () => { S.settings = await API.save_modes(S.settings.modes, S.settings.active_mode); renderHome(); }, 600);
});
$("#modeList").addEventListener("click", (e) => {
  const b = e.target.closest("[data-mact]"); if (!b) return;
  const id = b.closest(".mode-card").dataset.id, m = S.settings.modes.find((x) => x.id === id);
  if (b.dataset.mact === "default") { S.settings.active_mode = id; saveModes(); }
  if (b.dataset.mact === "key") startCapture("mode:" + id);
  if (b.dataset.mact === "nokey") { m.hotkey = ""; saveModes(); }
  if (b.dataset.mact === "del") modal("Delete this mode?", esc(m.name), [["Cancel", "ghost", () => {}],
    ["Delete", "primary", () => { S.settings.modes = S.settings.modes.filter((x) => x.id !== id); saveModes(); }]]);
});
$("#addMode").onclick = () => {
  S.settings.modes.push({ id: "m" + Date.now().toString(36), name: "New mode", icon: "sparkles", hotkey: "",
    instructions: "Describe how the AI should rewrite what you say, e.g. 'Translate into Spanish' or 'Write it as a tweet'." });
  saveModes();
};
$("#modeSel").onchange = (e) => saveSetting("active_mode", e.target.value);

// ---------- sync ----------
function renderSync() {
  const f = S.settings.sync_folder;
  $("#syncText").innerHTML = f ? `Syncing with <code>${esc(f)}</code>. Notes, history, AI modes and most settings are shared; the microphone, speech model and API key stay per PC.`
    : "Keep notes, history, AI modes and settings the same on several PCs: choose a folder that a sync service already keeps in step, such as OneDrive, Google Drive or Dropbox, on each PC.";
  $("#stopSync").hidden = !f; $("#pickSync").innerHTML = icon("folder") + (f ? "Change folder" : "Choose sync folder");
}
$("#pickSync").onclick = async () => {
  const r = await API.choose_sync_folder(); if (!r) return;
  Object.assign(S, r.state); renderAll();
  toast(r.existing ? "Joined the existing Parlo data in that folder" : "This PC's notes and history were copied to the sync folder");
};
$("#stopSync").onclick = () => modal("Stop syncing?", "Parlo copies everything back to this PC and stops using the shared folder. The folder is left as it is.", [
  ["Cancel", "ghost", () => {}], ["Stop syncing", "primary", async () => { Object.assign(S, await API.stop_sync()); renderAll(); toast("Sync stopped"); }]]);
document.addEventListener("keydown", (e) => {
  if (!S.capture) return;
  e.preventDefault();
  if (e.key === "Escape" && !S.capture.seen.length) return endCapture(false);
  const k = KEYMAP[e.key] || (e.key.length === 1 ? e.key.toLowerCase() : e.key.toLowerCase());
  S.capture.held.add(k);
  if (!S.capture.seen.includes(k)) S.capture.seen.push(k);
  const order = ["ctrl", "alt", "shift", "win"];
  S.capture.seen.sort((a, b) => (order.indexOf(a) + 1 || 9) - (order.indexOf(b) + 1 || 9));
  $("#captureKeys").innerHTML = keysHtml(S.capture.seen.join("+"));
}, true);
document.addEventListener("keyup", (e) => {
  if (!S.capture) return;
  e.preventDefault();
  S.capture.held.delete(KEYMAP[e.key] || e.key.toLowerCase());
  if (!S.capture.held.size && S.capture.seen.length) setTimeout(() => S.capture && endCapture(true), 150);
}, true);

// ---------- notes ----------
document.execCommand("defaultParagraphSeparator", false, "p");
function renderNotesList() {
  const q = $("#noteSearch").value.trim().toLowerCase();
  const list = S.notes.filter((n) => !q || (n.title + " " + n.preview).toLowerCase().includes(q));
  $("#noteItems").innerHTML = list.length ? list.map((n) => `<div class="nitem ${S.note && S.note.id === n.id ? "active" : ""}" data-id="${n.id}">
      <b>${esc(n.title || "Untitled note")}</b><small>${esc(n.preview || "Empty")}</small><span class="when">${when(n.updated)}</span></div>`).join("")
    : `<div class="muted small" style="padding:14px">${q ? "No matches." : "No notes yet."}</div>`;
  $("#editor").hidden = !S.note; $("#emptyNote").hidden = !!S.note;
}
$("#noteSearch").oninput = renderNotesList;
$("#noteItems").onclick = async (e) => { const it = e.target.closest(".nitem"); if (it) openNote(it.dataset.id); };
$("#newNote").onclick = $("#newNote2").onclick = () => newNote();
async function newNote(title = "", html = "") {
  await flushSave();
  const n = await API.note_new();
  n.title = title; n.html = html;
  S.notes.unshift({ id: n.id, title, preview: "", updated: n.updated });
  showNote(n);
  if (title || html) scheduleSave(0);
  $(title ? "#noteBody" : "#noteTitle").focus();
}
async function openNote(id) { await flushSave(); showNote(await API.note_get(id)); }
function showNote(n) {
  S.note = n; S.range = null;
  $("#noteTitle").value = n.title || ""; $("#noteBody").innerHTML = n.html || "";
  $("#savedTag").textContent = ""; renderNotesList();
}
function scheduleSave(ms = 600) { clearTimeout(S.saveTimer); $("#savedTag").textContent = "Editing…"; S.saveTimer = setTimeout(flushSave, ms); }
async function flushSave() {
  if (!S.note || !S.saveTimer) return;
  clearTimeout(S.saveTimer); S.saveTimer = null;
  const title = $("#noteTitle").value.trim(), html = $("#noteBody").innerHTML, preview = $("#noteBody").innerText.replace(/\s+/g, " ").trim();
  const updated = await API.note_save(S.note.id, title, html, preview);
  const entry = S.notes.find((x) => x.id === S.note.id);
  if (entry) Object.assign(entry, { title, preview: preview.slice(0, 160), updated });
  S.notes.sort((a, b) => b.updated - a.updated);
  $("#savedTag").textContent = "Saved"; renderNotesList();
}
$("#noteTitle").oninput = () => scheduleSave();
$("#noteTitle").onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); $("#noteBody").focus(); } };
$("#noteBody").oninput = () => scheduleSave();
document.addEventListener("selectionchange", () => {
  const sel = getSelection();
  if (sel.rangeCount && $("#noteBody").contains(sel.anchorNode)) { S.range = sel.getRangeAt(0).cloneRange(); updateToolbar(); }
});
function currentBlock() {
  let n = getSelection().anchorNode; const body = $("#noteBody");
  while (n && n !== body) { if (n.nodeType === 1 && /^(P|H1|H2|H3|LI|BLOCKQUOTE|DIV)$/.test(n.tagName)) return n; n = n.parentNode; }
  return null;
}
const inside = (tag) => { let n = getSelection().anchorNode; while (n && n.id !== "noteBody") { if (n.tagName === tag) return n; n = n.parentNode; } return null; };
function updateToolbar() {
  for (const c of ["bold", "italic", "underline", "strikeThrough", "insertUnorderedList", "insertOrderedList"])
    $(`.tb[data-cmd=${c}]`).classList.toggle("on", document.queryCommandState(c));
  const b = currentBlock();
  $$(".tb[data-block]").forEach((t) => t.classList.toggle("on", !!b && t.dataset.block !== "P" && (b.tagName === t.dataset.block || !!inside(t.dataset.block))));
}
$(".toolbar").addEventListener("mousedown", (e) => { if (e.target.closest(".tb")) e.preventDefault(); }); // keep the text selection
$$(".tb[data-cmd]").forEach((b) => (b.onclick = () => { document.execCommand(b.dataset.cmd); scheduleSave(); updateToolbar(); }));
$$(".tb[data-block]").forEach((b) => (b.onclick = () => {
  const tag = b.dataset.block, cur = currentBlock();
  const on = cur && (cur.tagName === tag || inside(tag));
  document.execCommand("formatBlock", false, on ? "P" : tag); scheduleSave(); updateToolbar();
}));
$("#checkBtn").onclick = () => {
  if (!inside("UL")) document.execCommand("insertUnorderedList");
  const ul = inside("UL"); if (ul) ul.classList.toggle("checklist"); scheduleSave();
};
$("#noteBody").addEventListener("click", (e) => {
  const li = e.target.closest("ul.checklist > li");
  if (li && e.clientX - li.getBoundingClientRect().left < 24) { li.classList.toggle("done"); scheduleSave(); }
});
$("#noteBody").addEventListener("paste", (e) => { // paste as plain text so notes keep one clean style
  e.preventDefault(); document.execCommand("insertText", false, e.clipboardData.getData("text/plain"));
});
$("#copyNote").onclick = async () => { await API.copy_text($("#noteBody").innerText); toast("Note copied as text"); };
$("#speakNote").onclick = () => API.speak($("#noteBody").innerText);
$("#exportNote").onclick = async () => {
  const name = ($("#noteTitle").value.trim() || "Note").replace(/[\\/:*?"<>|]/g, "") + ".md";
  const md = ($("#noteTitle").value.trim() ? `# ${$("#noteTitle").value.trim()}\n\n` : "") + toMarkdown($("#noteBody"));
  if (await API.save_text_file(name, md)) toast("Saved " + name);
};
$("#deleteNote").onclick = () => modal("Delete this note?", esc($("#noteTitle").value || "Untitled note"), [
  ["Cancel", "ghost", () => {}],
  ["Delete", "primary", async () => { clearTimeout(S.saveTimer); S.saveTimer = null; await API.note_delete(S.note.id);
    S.notes = S.notes.filter((n) => n.id !== S.note.id); S.note = null; renderNotesList(); }],
]);
$("#noteMic").onclick = () => { if (!$("#noteMic").classList.contains("busy")) API.note_record(); };

function toMarkdown(root) {
  const inline = (n) => [...n.childNodes].map((c) => {
    if (c.nodeType === 3) return c.textContent;
    const t = inline(c);
    return { B: `**${t}**`, STRONG: `**${t}**`, I: `*${t}*`, EM: `*${t}*`, S: `~~${t}~~`, STRIKE: `~~${t}~~`, BR: "\n" }[c.tagName] ?? t;
  }).join("");
  const out = [];
  for (const n of root.childNodes) {
    if (n.nodeType === 3) { if (n.textContent.trim()) out.push(n.textContent.trim()); continue; }
    const tag = n.tagName;
    if (tag === "H1") out.push("## " + inline(n)); // the note title is the only top-level heading
    else if (tag === "H2") out.push("### " + inline(n));
    else if (tag === "UL" || tag === "OL") out.push([...n.children].map((li, i) =>
      (tag === "OL" ? `${i + 1}. ` : n.classList.contains("checklist") ? (li.classList.contains("done") ? "- [x] " : "- [ ] ") : "- ") + inline(li)).join("\n"));
    else if (tag === "BLOCKQUOTE") out.push("> " + inline(n));
    else out.push(inline(n));
  }
  return out.filter((s) => s.trim()).join("\n\n") + "\n";
}

// Inserting dictated text with spoken formatting commands. Done with direct DOM edits rather
// than execCommand, so the result does not depend on focus or editing quirks.
function blockOf(node) {
  const body = $("#noteBody");
  for (let n = node; n && n !== body; n = n.parentNode)
    if (n.nodeType === 1 && /^(P|H1|H2|H3|LI|BLOCKQUOTE|DIV)$/.test(n.tagName)) return n;
  return null;
}
function topLevel(node) { const body = $("#noteBody"); while (node.parentNode !== body) node = node.parentNode; return node; }
function applyTokens(tokens) {
  if (!S.note) return;
  if (S.page !== "notes") go("notes");
  const body = $("#noteBody");
  let r;
  if (S.range && body.contains(S.range.startContainer)) r = S.range.cloneRange();
  else { r = document.createRange(); r.selectNodeContents(body); r.collapse(false); }
  let block = blockOf(r.startContainer);
  if (!block) { // caret directly in the body (empty note): start a paragraph
    block = document.createElement("p"); r.insertNode(block); r.selectNodeContents(block); r.collapse(false);
  }
  const caretTo = (el) => { block = el; r = document.createRange(); r.selectNodeContents(el); r.collapse(true); };
  const textBefore = () => { const x = document.createRange(); x.setStart(block, 0); x.setEnd(r.startContainer, r.startOffset); return x.toString(); };
  // a new block of `tag` after `after`; text that was after the caret moves into it
  const split = (tag, after) => {
    const rest = document.createRange(); rest.setStart(r.startContainer, r.startOffset); rest.setEnd(block, block.childNodes.length);
    const frag = rest.extractContents();
    const el = document.createElement(tag);
    if (frag.textContent.trim()) el.append(frag);
    after.after(el); caretTo(el); return el;
  };
  const emptyPara = () => block.tagName === "P" && !block.textContent.trim();
  for (const t of tokens) {
    if (t.t === "text") {
      [...block.childNodes].forEach((c) => { if (c.nodeName === "BR" && block.childNodes.length === 1) c.remove(); });
      const before = textBefore();
      const tn = document.createTextNode((before && !/\s$/.test(before) ? " " : "") + t.v);
      r.insertNode(tn); r.setStartAfter(tn); r.collapse(true);
    } else if (t.t === "line") {
      const br = document.createElement("br"); r.insertNode(br); r.setStartAfter(br); r.collapse(true);
    } else if (t.t === "para" || t.t === "endlist") {
      if (!emptyPara()) split("p", block.tagName === "LI" ? topLevel(block) : block);
    } else if (t.t === "bullet" || t.t === "number") {
      const tag = t.t === "bullet" ? "UL" : "OL";
      if (block.tagName === "LI" && block.parentNode.tagName === tag) split("li", block);
      else {
        const list = document.createElement(tag), li = document.createElement("li");
        list.append(li);
        if (emptyPara()) { block.replaceWith(list); caretTo(li); }
        else { const anchor = topLevel(block); const p = split("p", block); p.replaceWith(list);
               if (p.textContent.trim()) li.append(...p.childNodes); anchor.after(list); caretTo(li); }
      }
    } else if (t.t === "heading") {
      const h = document.createElement("h2");
      if (emptyPara()) { block.replaceWith(h); caretTo(h); }
      else { const p = split("p", block.tagName === "LI" ? topLevel(block) : block); h.append(...p.childNodes); p.replaceWith(h); caretTo(h); }
    }
  }
  body.focus();
  const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
  S.range = r.cloneRange();
  scheduleSave(300);
}

// ---------- activity dashboard ----------
const APP_NAMES = { "outlook.exe": "Outlook", "olk.exe": "Outlook", "slack.exe": "Slack", "chrome.exe": "Chrome", "msedge.exe": "Edge",
  "firefox.exe": "Firefox", "brave.exe": "Brave", "winword.exe": "Word", "code.exe": "VS Code", "notepad.exe": "Notepad",
  "teams.exe": "Teams", "ms-teams.exe": "Teams", "discord.exe": "Discord", "whatsapp.exe": "WhatsApp", "notion.exe": "Notion",
  "obsidian.exe": "Obsidian", "pythonw.exe": "Parlo", "python.exe": "Parlo", "claude.exe": "Claude", "excel.exe": "Excel", "powerpnt.exe": "PowerPoint" };
const appName = (exe) => APP_NAMES[exe] || exe.replace(/\.exe$/i, "").replace(/^./, (c) => c.toUpperCase());
function renderActivity() {
  const st = S.stats; if (!st || !st.days) return;
  const max = Math.max(1, ...st.days.map((d) => d.words));
  $("#actChart").innerHTML = st.days.map((d, i) => `<div class="bar ${i === st.days.length - 1 ? "today" : ""} ${d.words ? "" : "zero"}" title="${esc(d.date)}: ${d.words} words">
    <i style="height:${Math.max(3, (d.words / max) * 100)}%; --i:${i}"></i><small>${esc(d.date.slice(0, 2))}</small></div>`).join("");
  countTo($("#actStreak"), st.streak);
  countTo($("#actWpm"), st.wpm);
  $(".flame").classList.toggle("lit", st.streak >= 2);
  $("#actWeek").textContent = `${st.week_words.toLocaleString()} words in the last 7 days` + (st.best_day ? ` · best day ${st.best_day.date} (${st.best_day.words.toLocaleString()})` : "");
  $("#actApps").innerHTML = st.top_apps.length ? st.top_apps.map((a) => `<span class="tag">${esc(appName(a.app))} · ${a.words.toLocaleString()}</span>`).join("")
    : `<span class="muted small">The apps you dictate into most appear here.</span>`;
}

// ---------- per-app modes ----------
function appChips(m) {
  return `<div class="app-chips"><span class="muted small">Use automatically in</span>${(m.apps || []).map((a) =>
    `<span class="app-chip">${esc(appName(a))}<button data-mact="rmapp" data-app="${esc(a)}" title="Remove">${icon("x")}</button></span>`).join("")}
    <button class="btn ghost sm app-add" data-mact="addapp">${icon("plus")}App</button></div>`;
}
async function addAppDialog(modeId) {
  const recent = (await API.recent_apps()) || [];
  modal("Use this mode automatically in…", `<p class="muted small" style="margin:0 0 10px">When you dictate into one of these apps, Parlo switches to this mode by itself.</p>
    <div class="hf-files">${recent.map((a) => `<label><input type="checkbox" value="${esc(a)}"><span class="grow">${esc(appName(a))}</span><span class="muted small">${esc(a)}</span></label>`).join("")
      || `<p class="muted small">Dictate into a few apps first and they'll be listed here, or type the program name below.</p>`}</div>
    <input type="text" id="appExe" placeholder="or type a program, e.g. outlook.exe" spellcheck="false" style="width:100%;margin-top:10px">`,
    [["Cancel", "ghost", () => {}], ["Add", "primary", () => {
      const m = S.settings.modes.find((x) => x.id === modeId);
      const picked = $$("#modal input[type=checkbox]:checked").map((c) => c.value);
      const typed = $("#appExe").value.trim().toLowerCase();
      if (typed) picked.push(typed.endsWith(".exe") ? typed : typed + ".exe");
      if (!picked.length) return;
      S.settings.modes.forEach((o) => { o.apps = (o.apps || []).filter((a) => !picked.includes(a)); }); // one mode per app
      m.apps = [...new Set([...(m.apps || []), ...picked])];
      saveModes();
    }]]);
}
$("#modeList").addEventListener("click", (e) => {
  const b = e.target.closest("[data-mact=addapp], [data-mact=rmapp]"); if (!b) return;
  const id = b.closest(".mode-card").dataset.id, m = S.settings.modes.find((x) => x.id === id);
  if (b.dataset.mact === "addapp") addAppDialog(id);
  else { m.apps = (m.apps || []).filter((a) => a !== b.dataset.app); saveModes(); }
});

// ---------- settings: language, dictionary, walkthrough ----------
const LANGS = [["auto", "Detect automatically"], ["en", "English"], ["es", "Spanish"], ["fr", "French"], ["de", "German"], ["it", "Italian"],
  ["pt", "Portuguese"], ["nl", "Dutch"], ["pl", "Polish"], ["tr", "Turkish"], ["ru", "Russian"], ["uk", "Ukrainian"], ["ar", "Arabic"],
  ["hi", "Hindi"], ["zh", "Chinese"], ["ja", "Japanese"], ["ko", "Korean"], ["sv", "Swedish"], ["da", "Danish"], ["no", "Norwegian"], ["fi", "Finnish"]];
$("#langSel").innerHTML = LANGS.map(([v, n]) => `<option value="${v}">${n}</option>`).join("");
$("#langSel").onchange = (e) => saveSetting("language", e.target.value);
$("#saveDict").onclick = async () => { await saveSetting("dictionary", $("#dictText").value); toast("Dictionary saved", "check"); };
$("#replayTour").onclick = () => startTour();
function renderExtraSettings() {
  const s = S.settings; if (!s) return;
  $("#editKeys").innerHTML = keysHtml(s.edit_hotkey);
  $("#langSel").value = s.language || "auto";
  const multi = (S.models || []).some((m) => m.active && m.languages !== "English");
  $("#langNote").textContent = multi ? "Your model understands many languages." : "Other languages need a multilingual model, such as Whisper Large v3 Turbo.";
  if (document.activeElement !== $("#dictText")) $("#dictText").value = s.dictionary || "";
}

// ---------- meeting recorder ----------
let meetTimer = null;
function renderMeeting() {
  const m = S.meeting, btn = $("#meetBtn");
  btn.classList.toggle("live", !!m && m.state === "recording");
  btn.classList.toggle("busy", !!m && m.state === "summarising");
  clearInterval(meetTimer);
  if (m && m.state === "recording") {
    const tick = () => { const s = Math.max(0, Math.floor(Date.now() / 1000 - m.start)); $("#meetLabel").textContent = `Stop · ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
    tick(); meetTimer = setInterval(tick, 1000);
  } else $("#meetLabel").textContent = m && m.state === "summarising" ? "Writing the summary…" : "Record a meeting";
  const live = !!m && !!S.note && S.note.id === m.note_id;
  $("#noteBody").contentEditable = live ? "false" : "true";
}
$("#meetBtn").onclick = async () => {
  if (S.meeting && S.meeting.state === "summarising") return;
  if (S.meeting) { API.meeting_stop(); S.meeting.state = "summarising"; renderMeeting(); return; }
  const r = await API.meeting_start();
  if (!r || r.error) return toast((r && r.error) || "Could not start recording");
  S.meeting = { ...(S.meeting || {}), note_id: r.note_id, state: "recording", start: S.meeting?.start || Date.now() / 1000 };
  await openNote(r.note_id); renderMeeting();
  toast("Recording. The transcript is added every 30 seconds.", "mic");
};
function onMeeting(d) {
  S.meeting = d.state === "done" ? null : { ...(S.meeting || {}), ...d };
  if (d.html && S.note && S.note.id === d.note_id) { $("#noteBody").innerHTML = d.html; S.note.html = d.html; }
  if (d.state === "done") toast("Meeting saved with a summary", "check");
  renderMeeting();
}

// ---------- first-run walkthrough ----------
let tourStep = 0, tourWatch = null;
const TOUR = [
  () => `<img class="big-logo" src="logo.svg" alt=""><h2>Welcome to Parlo</h2>
    <p>Talk, and your words appear in any app: emails, chats, documents. Everything runs on this PC: no account, no cloud, free.</p>
    <p class="muted">This quick tour checks your microphone and gets you dictating in under a minute.</p>`,
  () => `<h2>${icon("mic")}Check your microphone</h2><p>Say something. The bar should move while you talk.</p>
    <div class="meter"><i id="tourMeter"></i></div>
    <div class="setting"><div><b>Microphone</b></div><select id="tourMic"><option value="">System default</option>${(S.mics || []).map((m) => `<option ${m === S.settings.microphone ? "selected" : ""}>${esc(m)}</option>`).join("")}</select></div>`,
  () => `<h2>${icon("keyboard")}Try your first dictation</h2>
    <p>Click in the box, press <span class="keys">${keysHtml(S.settings.dictate_hotkey)}</span>, say <i>"Hello Parlo, this is my first dictation"</i>, then press it again.</p>
    <textarea id="tourBox" rows="3" placeholder="Your words will appear here…"></textarea><p id="tourOk"></p>`,
  () => `<h2>${icon("sparkles")}Make it yours</h2>
    <p><b>AI modes</b> can remove filler words or turn rambling into an email, free on your PC. Pick how Parlo starts:</p>
    <div class="seg" id="tourMode"><button data-v="plain">Exactly what I say</button><button data-v="clean">Clean up</button></div>
    <p class="muted" style="margin-top:14px">Also worth a look: <b>Notes</b> for voice notes and meetings, <b>Read aloud</b> for natural voices, and
      <b>Settings</b> for your dictionary, the floating mic button and start with Windows.</p>`,
];
function startTour() { tourStep = 0; $("#tour").hidden = false; renderTour(); }
function renderTour() {
  clearInterval(tourWatch);
  $("#tourDots").innerHTML = TOUR.map((_, i) => `<i class="${i === tourStep ? "on" : ""}"></i>`).join("");
  const body = $("#tourBody"); body.innerHTML = TOUR[tourStep]();
  body.style.animation = "none"; void body.offsetWidth; body.style.animation = "";
  $("#tourBack").hidden = tourStep === 0;
  $("#tourNext").textContent = tourStep === TOUR.length - 1 ? "Start using Parlo" : "Next";
  API.mic_test(tourStep === 1);
  if (tourStep === 1) $("#tourMic").onchange = async (e) => { await saveSetting("microphone", e.target.value || null); await API.mic_test(false); API.mic_test(true); };
  if (tourStep === 2) {
    const count = S.history.length; $("#tourBox").focus();
    tourWatch = setInterval(() => {
      if (S.history.length > count) { $("#tourOk").innerHTML = `<span class="ok">${icon("check")}That worked. You're ready.</span>`; clearInterval(tourWatch); }
    }, 300);
  }
  if (tourStep === 3) {
    $$("#tourMode button").forEach((b) => b.classList.toggle("on", b.dataset.v === S.settings.active_mode));
    $("#tourMode").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; saveSetting("active_mode", b.dataset.v); $$("#tourMode button").forEach((x) => x.classList.toggle("on", x === b)); };
  }
}
async function endTour() { clearInterval(tourWatch); API.mic_test(false); $("#tour").hidden = true; await saveSetting("onboarded", true); }
$("#tourNext").onclick = () => { if (tourStep < TOUR.length - 1) { tourStep++; renderTour(); } else endTour(); };
$("#tourBack").onclick = () => { if (tourStep > 0) { tourStep--; renderTour(); } };
$("#tourSkip").onclick = endTour;

// ---------- demo mode (opened in a normal browser, for design work) ----------
function demoApi() {
  const now = Date.now() / 1000;
  const st = {
    settings: { model: "bark-3.0", dictate_hotkey: "ctrl+win", read_hotkey: "ctrl+alt+r", activation: "automatic", action: "autoInsert", insert_method: "paste",
      microphone: null, sounds: true, tidy: true, trailing_space: true, replacements: "open ai => OpenAI", voice: "Microsoft Zira Desktop", rate: 0, theme: "dark",
      tts_engine: "kokoro", kokoro_voice: "af_heart",
      overlay_style: "pill", live_preview: true, sync_folder: "", ai_provider: "local", llm_model: "qwen2.5-1.5b", ai_model: "", ai_base_url: "", ai_key_set: false, active_mode: "clean",
      dictionary: "Parlo\nKubernetes", language: "auto", edit_hotkey: "ctrl+alt+space", voice_actions: true, widget: false, start_with_windows: false, onboarded: true,
      modes: [{ id: "plain", name: "Plain dictation", hotkey: "", instructions: "" },
              { id: "clean", name: "Clean up", hotkey: "", instructions: "Remove filler words, false starts and repetitions. Fix grammar and punctuation." },
              { id: "email", name: "Email", hotkey: "ctrl+alt+e", apps: ["outlook.exe"], instructions: "Turn this into a clear, friendly email body with short paragraphs." }] },
    llms: [{ id: "qwen2.5-1.5b", name: "Qwen2.5 1.5B", family: "Qwen", license: "Apache-2.0", ram_gb: 1.7, accuracy: 3, speed: 5, secs: "1-2 s", size_mb: 1066, installed: true, active: true, loaded: true, blurb: "Recommended. Fast on any everyday PC; good clean-ups and bullet lists." },
           { id: "qwen3-1.7b", name: "Qwen3 1.7B", family: "Qwen", license: "Apache-2.0", ram_gb: 2, accuracy: 4, speed: 3, secs: "3-4 s", size_mb: 1749, installed: true, active: false, blurb: "Sticks most closely to your own words. A little slower." },
           { id: "custom-qwen3-8b-q4_k_m", name: "Qwen3-8B-Q4_K_M", family: "Qwen", license: "apache-2.0", ram_gb: 6.0, accuracy: 0, speed: 0, secs: "untested", size_mb: 4790, installed: true, active: false, custom: true, blurb: "Your own model from Qwen/Qwen3-8B-GGUF. Untested by Parlo." },
           { id: "qwen3-4b", name: "Qwen3 4B", family: "Qwen", license: "Apache-2.0", ram_gb: 3.5, accuracy: 5, speed: 2, secs: "~8 s", size_mb: 2382, installed: false, active: false, blurb: "Best writing quality, for rewrites like emails. Needs a stronger PC with 16 GB RAM." }],
    tts: { installed: true, size_mb: 116, voices: ["af_bella", "af_heart", "af_nicole", "am_michael", "bf_emma", "bm_george", "ff_siwis"] },
    providers: { local: { name: "On this PC (free)", note: "Free, private and offline: a small AI model runs on your own computer." }, groq: { name: "Groq", model: "llama-3.3-70b-versatile", note: "Free tier available. Very fast.", key_url: "x" },
                 ollama: { name: "Ollama (on this PC)", model: "llama3.2:3b", base: "http://localhost:11434/v1", note: "Free and private." } },
    status: { engine: "ready", model: "Bark 3.0", model_id: "bark-3.0", state: "idle", target: "insert" },
    stats: { today_words: 412, total_words: 18230, count: 964, saved_min: 395, streak: 6, wpm: 142, week_words: 3120,
      best_day: { date: "Thu 22 Oct", words: 806 }, top_apps: [{ app: "outlook.exe", words: 6120 }, { app: "slack.exe", words: 4210 }, { app: "code.exe", words: 1990 }],
      days: [120, 0, 340, 512, 280, 0, 0, 430, 610, 806, 390, 0, 470, 412].map((w, i) => ({ date: new Date((now - (13 - i) * 86400) * 1000).toDateString().slice(0, 10), words: w })) },
    history: [
      { t: now - 60, text: "Please send the quarterly report to the finance team by Friday.", secs: 5.5, app: "outlook.exe" },
      { t: now - 3600, text: "I would like two coffees and a blueberry muffin, thank you.", secs: 4.5 },
      { t: now - 7200, text: "Remind me to call the landlord about the boiler tomorrow morning.", secs: 4.1 },
      { t: now - 90000, text: "The new design looks a lot cleaner. Let's ship it on Monday.", secs: 3.9 },
    ],
    voices: ["Microsoft Zira Desktop", "Microsoft David Desktop"], mics: ["Microphone (UGREEN USB MIC-CM58)"],
    notes: [{ id: "a", title: "Project kickoff", preview: "Goals for the first sprint, owners and dates…", updated: now - 500 },
            { id: "b", title: "Shopping", preview: "Milk, eggs, coffee beans", updated: now - 86400 }],
    models: [
      { id: "bark-3.0", name: "Bark 3.0", family: "Parakeet", languages: "English", ram_gb: 3.2, accuracy: 4, speed: 4, license: "CC-BY-4.0", size_mb: 156, installed: true, active: true, blurb: "Recommended. Very accurate English dictation with punctuation, in a small download." },
      { id: "bark-3.0-plus", name: "Bark 3.0 Plus", family: "Parakeet", languages: "English", ram_gb: 3.3, accuracy: 5, speed: 4, license: "CC-BY-4.0", size_mb: 171, installed: false, active: false, blurb: "A little more accurate than Bark 3.0 for a slightly bigger download.", download: { progress: .42, state: "downloading" } },
      { id: "whisper-base.en", name: "Whisper Base", family: "Whisper", languages: "English", ram_gb: .5, accuracy: 2, speed: 5, license: "MIT", size_mb: 141, installed: true, active: false, blurb: "Tiny and very fast. Good for older or low-memory PCs; makes more mistakes." },
      { id: "whisper-large-v3-turbo", name: "Whisper Large v3 Turbo", family: "Whisper", languages: "99 languages", ram_gb: 2, accuracy: 4, speed: 2, license: "MIT", size_mb: 1546, installed: false, active: false, blurb: "The one to pick for languages other than English. Slower on CPU." },
    ],
  };
  const notes = { a: { id: "a", title: "Project kickoff", html: "<h2>Goals</h2><ul><li>Ship the redesigned app</li><li>Add <b>voice notes</b> with formatting</li></ul><p>Owners are confirmed for each workstream.</p><ul class='checklist'><li class='done'>Book the room</li><li>Send the agenda</li></ul>", updated: now - 500 },
                  b: { id: "b", title: "Shopping", html: "<ul><li>Milk</li><li>Eggs</li><li>Coffee beans</li></ul>", updated: now - 86400 } };
  const ok = (v) => Promise.resolve(v);
  return new Proxy({}, { get: (_, name) => ({
    ui_ready: () => ok(st), note_get: (id) => ok(notes[id]), note_new: () => ok({ id: Math.random().toString(16).slice(2), title: "", html: "", updated: Date.now() / 1000 }),
    note_save: () => ok(Date.now() / 1000), save_settings: (c) => ok(Object.assign(st.settings, c)),
    save_modes: (m, a) => ok(Object.assign(st.settings, { modes: m, active_mode: a })), save_ai: () => ok(st.settings),
    inspect_hf: () => ok({ ok: true, repo: "Qwen/Qwen3-8B-GGUF", license: "apache-2.0", choices: [{ file: "Qwen3-8B-Q4_K_M.gguf", mb: 4790 }, { file: "Qwen3-8B-Q5_K_M.gguf", mb: 5600 }, { file: "Qwen3-8B-Q8_0.gguf", mb: 8340 }] }), delete_history: () => ok(st.stats), clear_history: () => ok(st.stats),
    engine_memory: () => ok(3150), recent_apps: () => ok(["outlook.exe", "slack.exe", "chrome.exe"]),
    meeting_start: () => { setTimeout(() => window.onBark("meeting", { note_id: "a", state: "recording", start: Date.now() / 1000, html: "<h2>Transcript</h2><p><b>[00:00:00]</b> Okay, let's get started with the weekly sync.</p>" }), 400); return ok({ note_id: "a" }); }, note_record: () => { setTimeout(() => window.onBark("note_insert", [{ t: "text", v: "Here is a dictated sentence." }, { t: "bullet" }, { t: "text", v: "First point" }]), 300); return ok(); },
  }[name] || (() => ok(null))) });
}
