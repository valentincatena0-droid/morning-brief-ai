/* Morning Brief AI — vanilla-JS PWA. No build step, no third-party code, no secrets.
   All text is inserted with textContent (never innerHTML) so feed content cannot inject markup. */
"use strict";

const $app = document.getElementById("app");
const INTERESTS = ["World", "USA", "Politics", "Economy", "Business", "Technology", "AI", "Science", "Space", "Climate", "Sports", "Entertainment", "Gaming", "Crypto", "Local"];
const CAT_LABEL = { world: "World", usa: "USA", economy: "Economy", technology: "Tech", science: "Science", health: "Health", security: "Security", climate: "Climate", sports: "Sports", culture: "Culture" };
const SEC_ICON = { world: "🌎", usa: "🇺🇸", economy: "💰", technology: "🤖", science: "🔬", climate: "🌍", sports: "⚽", culture: "🎭" };
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

/* ---------- tiny helpers ---------- */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const safeUrl = (u) => { try { const x = new URL(u); return /^https?:$/.test(x.protocol) ? x.href : "#"; } catch { return "#"; } };
const ext = (url, cls, ...kids) => h("a", { href: safeUrl(url), target: "_blank", rel: "noopener noreferrer", class: cls }, ...kids);
const store = {
  get(k, d) { try { const v = localStorage.getItem("mb." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("mb." + k, JSON.stringify(v)); } catch { /* private mode */ } },
};
const prefs = () => ({
  interests: store.get("interests", INTERESTS.map((i) => i.toLowerCase())),
  personalize: store.get("personalize", true),
  theme: store.get("theme", "dark"),
  watchlist: store.get("watchlist", ["S&P 500", "Nasdaq", "Federal Reserve", "oil", "gold", "bitcoin"]),
  finance_on: store.get("finance_on", true),
  mem: store.get("mem", { cat: {}, opened: {} }),
});
function applyTheme() {
  const t = prefs().theme;
  const dark = t === "dark" || (t === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.querySelector('meta[name="theme-color"]').content = dark ? "#0a0c10" : "#f4f6fa";
}
async function getJSON(path) {
  const r = await fetch(path, { cache: "no-cache" });
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}
const fmtTime = (iso) => new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
const greeting = () => { const hr = new Date().getHours(); return hr < 12 ? "GOOD MORNING" : hr < 18 ? "GOOD AFTERNOON" : "GOOD EVENING"; };
const highlight = (text, q) => {
  if (!q) return [text];
  const terms = q.toLowerCase().split(/\s+/).filter((t) => t.length > 1);
  if (!terms.length) return [text];
  const rx = new RegExp("(" + terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "ig");
  return text.split(rx).map((p, i) => (i % 2 ? h("mark", { text: p }) : p));
};

/* ---------- personalisation (bounded, anti-bubble) ---------- */
function personalize(brief) {
  const p = prefs();
  const all = [...brief.stories, ...(brief.pool || [])];
  const base = brief.stories.length;
  if (!p.personalize) return brief.stories;
  const want = new Set(p.interests);
  const boost = (s) => {
    const tags = new Set([s.category, ...(s.tags || [])]);
    const hit = [...tags].filter((t) => want.has(t)).length;
    const mem = p.mem.cat[s.category] || 0;
    return Math.min(hit * 4, 10) + Math.min(mem * 0.5, 3);        // bounded: interests can never outrank importance by much
  };
  const chosen = [];
  const mustKnow = all.filter((s) => s.must_know).sort((a, b) => b.score - a.score);
  for (const s of mustKnow) if (chosen.length < base) chosen.push(s);    // important news is never dropped
  const explore = Math.min(2, base);                                     // 2 slots reserved for pure importance
  const rest = all.filter((s) => !chosen.includes(s));
  const byBoost = [...rest].sort((a, b) => b.score + boost(b) - (a.score + boost(a)));
  while (chosen.length < base - explore && byBoost.length) chosen.push(byBoost.shift());
  const byScore = rest.filter((s) => !chosen.includes(s)).sort((a, b) => b.score - a.score);
  while (chosen.length < base && byScore.length) chosen.push(byScore.shift());
  return chosen.sort((a, b) => b.score - a.score).map((s, i) => ({ ...s, position: i + 1 }));
}

/* ---------- views ---------- */
function chips(s) {
  return h("div", { class: "story-top" },
    h("span", { class: "num", text: String(s.position || "•").padStart(2, "0") }),
    (s.priority === "BREAKING" || s.priority === "URGENT") && h("span", { class: "chip prio " + s.priority, text: s.priority }),
    h("span", { class: "chip " + s.status, text: s.status_label.es }),
    h("span", { class: "chip", text: CAT_LABEL[s.category] || s.category }));
}
function storyCard(s, date, wl) {
  const hit = wl && wl.some((w) => (s.headline + " " + s.summary).toLowerCase().includes(w.toLowerCase()));
  return h("a", { class: "card story" + (hit ? " hl" : ""), href: `#/story/${date}/${s.id}` },
    chips(s), h("h2", { text: s.headline }), h("p", { text: s.summary }),
    h("div", { class: "meta", text: `${s.independent_sources} source${s.independent_sources === 1 ? "" : "s"} · ${s.sources.slice(0, 3).map((x) => x.name).join(" · ")}` }));
}
function masthead(brief, extra) {
  return h("header", { class: "masthead" },
    h("div", { class: "eyebrow", text: greeting() }),
    h("h1", { text: "Morning Brief" }),
    h("div", { class: "date", text: brief.date_label_es }),
    h("div", { class: "sub", text: brief.subtitle }), extra, h("div", { class: "rule" }));
}
function briefView(brief, { list, readonly }) {
  const frag = h("div");
  frag.append(masthead(brief));
  const tzWarn = brief.timezone && Intl.DateTimeFormat().resolvedOptions().timeZone !== brief.timezone && !readonly;
  if (tzWarn) frag.append(h("div", { class: "banner info", text: `Brief runs on ${brief.timezone}; your device is on ${Intl.DateTimeFormat().resolvedOptions().timeZone}. Change it in Settings if you travel.` }));
  for (const w of brief.warnings || []) frag.append(h("div", { class: "banner", text: "⚠ " + w }));
  for (const s of list) frag.append(storyCard(s, brief.date, null));
  const pool = new Map([...brief.stories, ...(brief.pool || [])].map((x) => [x.id, x]));
  for (const n of brief.niches || []) {
    const rows = n.story_ids.map((id) => pool.get(id)).filter(Boolean);
    if (!rows.length) continue;
    const box = h("div", { class: "card sec" }, h("h3", { text: n.name }), h("p", { class: "meta", text: n.subtitle }));
    rows.slice(0, 3).forEach((r) => box.append(h("a", { class: "row", href: `#/story/${brief.date}/${r.id}`, text: r.headline })));
    box.append(h("a", { class: "row", href: `#/niche/${n.id}`, text: `Ver todo: ${n.name} ›` }));
    frag.append(h("div", { class: "label", text: "Para ti" }), box);
  }
  const ids = new Set(list.map((s) => s.id));
  const secs = h("div", { class: "card sec" });
  let any = false;
  for (const [cat, rows] of Object.entries(brief.sections || {})) {
    if (!rows.length) continue;
    any = true;
    secs.append(h("h3", { text: `${SEC_ICON[cat] || ""} ${cat.toUpperCase()}` }));
    rows.forEach((r) => secs.append(h("a", { class: "row", href: `#/story/${brief.date}/${r.id}`, text: r.headline })));
  }
  if (any) frag.append(h("div", { class: "label", text: "More by section" }), secs);
  if (brief.biggest_story) {
    const b = brief.biggest_story;
    frag.append(h("div", { class: "label", text: "The biggest story" }),
      h("a", { class: "card big story", href: `#/story/${brief.date}/${b.story_id}` }, h("h2", { text: b.headline }), h("p", { text: b.description }),
        h("div", { class: "meta", text: b.coverage })));
  }
  frag.append(h("p", { class: "meta", text: `Generated ${fmtTime(brief.generated_at)} · ${brief.stats.feeds_ok}/${brief.stats.feeds_total} feeds · ordering uses importance and verification, not clicks.` }));
  return frag;
}

async function viewToday() {
  const brief = await getJSON("data/latest.json");
  checkNew(brief);
  return briefView(brief, { list: personalize(brief) });
}
async function viewDay(date) {
  const brief = await getJSON(`data/briefs/${date}.json`);
  const v = briefView(brief, { list: brief.stories, readonly: true });
  v.prepend(h("a", { class: "back", href: "#/history", text: "‹ History" }));
  return v;
}

async function findStory(date, id) {
  let b = null;
  try { b = date === "latest" ? await getJSON("data/latest.json") : await getJSON(`data/briefs/${date}.json`); } catch { /* fall through to alerts */ }
  let s = b && [...b.stories, ...(b.pool || [])].find((x) => x.id === id);
  if (!s) { try { s = (await getJSON("data/alerts.json")).find((x) => x.id === id); } catch { /* none */ } }
  if (!s) { try { const l = await getJSON("data/latest.json"); s = [...l.stories, ...(l.pool || [])].find((x) => x.id === id); b = l; } catch { /* none */ } }
  return { s, date: b ? b.date : date };
}

function groundedPrompt(s, mode) {
  const facts = s.know.map((k) => `- (${k.source}, ${k.kind}) ${k.text}`).join("\n");
  const ask = {
    beginner: "Explain this news as if I have never studied the subject. Plain language, no jargon.",
    conseq: "What could the consequences be? Give cautious, clearly hypothetical possibilities and what would make each more or less likely.",
    context: "Give neutral background context that helps me understand why this happened.",
  }[mode];
  return `${ask}\n\nRules: use ONLY the facts below. Separate your answer into three headed sections: FACTS, POSSIBLE CONSEQUENCES, ANALYSIS. Attribute political statements ("X said"), say when something is unknown, do not invent numbers, names or quotes.\n\nHEADLINE: ${s.headline}\nSTATUS: ${s.status_label.en}\nFACTS:\n${facts}\nSTILL UNKNOWN:\n${s.unknown.map((u) => "- " + u).join("\n")}\nSOURCES:\n${s.sources.map((x) => `- ${x.name}: ${x.url}`).join("\n")}`;
}
function explainPanel(s) {
  const box = h("div", { class: "explain" });
  let mode = "beginner";
  const body = h("div");
  const modes = { beginner: "Like I'm new to it", conseq: "Consequences", context: "Background" };
  const seg = h("div", { class: "seg" });
  const render = () => {
    seg.replaceChildren(...Object.entries(modes).map(([k, v]) => h("button", { class: k === mode ? "on" : "", text: v, onclick: () => { mode = k; render(); } })));
    body.replaceChildren(
      h("h3", { text: "Facts" }),
      h("p", { text: s.know.map((k) => `${k.text} (${k.source})`).join("  ") }),
      h("h3", { text: "Possible consequences" }),
      h("p", { text: s.explain && s.explain.possible_consequences.length ? s.explain.possible_consequences.join(" · ") : "Not stated by the sources, so none is shown as fact. Use the prompt below with an AI assistant to explore hypotheticals." }),
      h("h3", { text: "Analysis" }),
      h("p", { text: s.explain ? s.explain.analysis || s.explain.simple : "No automated analysis is generated by default (nothing is invented). Copy the grounded prompt to get one that stays within these facts." }),
      ...(s.explain ? [h("h3", { text: "Plain explanation (AI, grounded on the source excerpts)" }), h("p", { text: s.explain.simple })] : []));
    const ta = h("textarea", { class: "prompt", readonly: true }); ta.value = groundedPrompt(s, mode);
    body.append(h("h3", { text: "Ask an AI (grounded prompt)" }), ta,
      h("div", { class: "btnrow" }, h("button", { class: "btn", text: "Copy prompt", onclick: async (e) => { try { await navigator.clipboard.writeText(ta.value); e.target.textContent = "Copied ✓"; } catch { ta.select(); } } })));
  };
  render();
  box.append(seg, body);
  return box;
}

async function viewStory(date, id) {
  const { s, date: d } = await findStory(date, id);
  if (!s) return h("div", { class: "empty", text: "Story not found." });
  const mem = prefs().mem; mem.cat[s.category] = (mem.cat[s.category] || 0) + 1; mem.opened[s.id] = 1; store.set("mem", mem);
  const v = h("div", { class: "detail" });
  v.append(h("a", { class: "back", href: "#/today", text: "‹ Back", onclick: (e) => { e.preventDefault(); history.length > 1 ? history.back() : (location.hash = "#/today"); } }), chips({ ...s, position: s.position }),
    h("h1", { text: s.headline }), h("p", { class: "lead", text: s.summary }),
    h("div", { class: "label", text: "Why it matters" }), h("p", { class: "lead", text: s.why_it_matters }));
  if (s.political_note) v.append(h("div", { class: "banner info", text: s.political_note }));
  v.append(h("div", { class: "label", text: "What we know" }),
    h("ul", { class: "list" }, s.know.map((k) => h("li", null, k.text, h("span", { class: "kind " + (k.kind === "Reported" ? "" : k.kind === "Contested" ? "ct" : "uc"), text: k.kind }), h("span", { class: "by", text: k.source })))),
    h("div", { class: "label", text: "What we don't know yet" }),
    h("ul", { class: "list unk" }, s.unknown.map((u) => h("li", { text: u }))));
  const exp = h("div");
  v.append(h("div", { class: "btnrow" }, ext(s.read_original, "btn primary", "Read original ↗"),
    h("button", { class: "btn", text: "Explain", onclick: () => { exp.firstChild ? exp.replaceChildren() : exp.append(explainPanel(s)); } })), exp);
  v.append(h("div", { class: "label", text: `Sources (${s.sources.length})` }),
    h("div", { class: "card" }, s.sources.map((x) => ext(x.url, "src", h("span", null, x.name + (x.primary ? " · primary" : ""), h("small", { text: x.title })), h("span", { class: "trust", text: "↗" })))));
  v.append(h("p", { class: "meta", text: `Verification: ${s.status_label.en} · ${s.independent_sources} independent source(s)${s.has_primary ? " incl. primary" : ""}. ${(s.verification_notes || []).join("; ")}.` }));
  return v;
}

async function viewHistory() {
  const idx = await getJSON("data/index.json");
  const v = h("div", null, h("header", { class: "masthead" }, h("div", { class: "eyebrow", text: "Archive" }), h("h1", { text: "History" })));
  if (!idx.length) v.append(h("div", { class: "empty", text: "No briefs yet." }));
  for (const d of idx) v.append(h("a", { class: "card hist", href: `#/day/${d.date}` }, h("h2", { text: d.label }), h("p", { text: d.headlines.slice(0, 3).join(" · ") }), h("div", { class: "meta", text: `${d.count} stories` })));
  return v;
}

function parseDateQuery(q) {
  const m = q.match(/\b(20\d\d)-(\d\d)-(\d\d)\b/);
  if (m) return m[0];
  const months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
  const n = q.toLowerCase().match(/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b/);
  if (n) return { m: months.indexOf(n[1]) + 1, d: +n[2] };
  return null;
}
let searchCache = null;
async function viewSearch() {
  const v = h("div", null, h("header", { class: "masthead" }, h("div", { class: "eyebrow", text: "Search news" }), h("h1", { text: "Search" })));
  const input = h("input", { type: "search", placeholder: "Person, company, event or date (e.g. Fed, 2026-09-20)", autocomplete: "off", autocapitalize: "off", enterkeyhint: "search" });
  const out = h("div");
  v.append(input, out);
  const run = async () => {
    const q = input.value.trim();
    out.replaceChildren();
    if (q.length < 2) return out.append(h("div", { class: "empty", text: "Search every brief in your archive." }));
    searchCache = searchCache || (await getJSON("data/search.json"));
    const dq = parseDateQuery(q);
    const terms = q.toLowerCase().replace(/\b(20\d\d-\d\d-\d\d)\b/, "").split(/\s+/).filter((t) => t.length > 1 && !(dq && typeof dq === "object" && /^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|^\d{1,2}$/.test(t)));
    const rows = searchCache.map((e) => {
      const date = e.d;
      if (dq) {
        if (typeof dq === "string" ? date !== dq : !(+date.slice(5, 7) === dq.m && +date.slice(8, 10) === dq.d)) return null;
      }
      const hay = (e.h + " " + e.s + " " + e.src.join(" ")).toLowerCase();
      if (!terms.every((t) => hay.includes(t))) return null;
      const sc = terms.reduce((a, t) => a + (e.h.toLowerCase().includes(t) ? 3 : 1), 0) + (e.top ? 1 : 0);
      return { e, sc };
    }).filter(Boolean).sort((a, b) => b.sc - a.sc || (a.e.d < b.e.d ? 1 : -1)).slice(0, 60);
    if (!rows.length) return out.append(h("div", { class: "empty", text: "No matches in the archive." }));
    out.append(h("p", { class: "meta", text: `${rows.length}${rows.length === 60 ? "+" : ""} result(s)` }));
    for (const { e } of rows) out.append(h("a", { class: "card result", href: `#/story/${e.d}/${e.id}` },
      h("div", { class: "d", text: `${e.d} · ${CAT_LABEL[e.c] || e.c}` }), h("h2", null, ...highlight(e.h, q)), h("p", null, ...highlight(e.s, q)),
      h("div", { class: "meta", text: e.src.join(" · ") })));
  };
  let t; input.addEventListener("input", () => { clearTimeout(t); t = setTimeout(run, 160); });
  run();
  return v;
}

async function viewNiche(id) {
  const brief = await getJSON("data/latest.json");
  const n = (brief.niches || []).find((x) => x.id === id);
  const v = h("div", null, h("a", { class: "back", href: "#/today", text: "‹ Today" }));
  if (!n) { v.append(h("div", { class: "empty", text: "Esta edición no está disponible hoy." })); return v; }
  v.append(h("header", { class: "masthead" }, h("div", { class: "eyebrow", text: "Edición especial" }), h("h1", { text: n.name }), h("div", { class: "sub", text: n.subtitle }), h("div", { class: "rule" })));
  const pool = new Map([...brief.stories, ...(brief.pool || [])].map((x) => [x.id, x]));
  n.story_ids.map((i) => pool.get(i)).filter(Boolean).forEach((s) => v.append(storyCard(s, brief.date, null)));
  try {
    const dist = await getJSON("data/distribution.json");
    const box = h("div", { class: "card" }, h("div", { class: "label", text: "Compartir esta edición (gratis)" }));
    const row = h("div", { class: "btnrow" });
    row.append(h("button", { class: "btn", text: "Copiar texto", onclick: async (e) => { try { const t = await (await fetch(`data/out/${id}.txt`, { cache: "no-store" })).text(); await navigator.clipboard.writeText(t); e.target.textContent = "¡Copiado!"; } catch { e.target.textContent = "No se pudo copiar"; } } }));
    row.append(h("a", { class: "btn", href: `data/feeds/${id}.xml`, text: "RSS" }));
    const ch = dist.channels || {};
    if (ch.telegram_url) row.append(h("a", { class: "btn", href: ch.telegram_url, text: "Telegram" }));
    if (ch.newsletter_url) row.append(h("a", { class: "btn", href: ch.newsletter_url, text: "Newsletter" }));
    if (ch.support_url) row.append(h("a", { class: "btn", href: ch.support_url, text: "Apoyar" }));
    box.append(row);
    v.append(box);
  } catch { /* distribution kit not built yet */ }
  v.append(h("p", { class: "meta", text: "Selección de las noticias verificadas de hoy, con prioridad a fuentes oficiales. Es información, no asesoría financiera, médica ni legal." }));
  return v;
}

async function viewFinance() {
  const p = prefs();
  const v = h("div", null, h("header", { class: "masthead" }, h("div", { class: "eyebrow", text: "Markets & economy" }), h("h1", { text: "Finance" })));
  v.append(h("div", { class: "card guard" }, h("div", { class: "label", text: "Read-only" }),
    h("p", { class: "lead", text: "This app only reports financial news. It cannot buy, sell, transfer, invest or pay, and it has no access to any account. Any action with money involved would always require your explicit confirmation." })));
  v.append(h("div", { class: "card" }, h("div", { class: "toggle" }, h("span", null, "Show financial news", h("small", { text: "Economy, markets, business and crypto stories from today's brief." })),
    h("input", { type: "checkbox", class: "sw", checked: p.finance_on, onchange: (e) => { store.set("finance_on", e.target.checked); route(); } }))));
  const wl = h("div", { class: "chips" });
  const drawWl = () => { wl.replaceChildren(...prefs().watchlist.map((w) => h("button", { class: "on", text: w + " ×", onclick: () => { store.set("watchlist", prefs().watchlist.filter((x) => x !== w)); drawWl(); } }))); };
  const inp = h("input", { type: "text", placeholder: "Add a keyword (company, index, commodity…)", enterkeyhint: "done" });
  inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && inp.value.trim()) { store.set("watchlist", [...new Set([...prefs().watchlist, inp.value.trim()])]); inp.value = ""; drawWl(); } });
  drawWl();
  v.append(h("div", { class: "label", text: "Watch keywords (highlight only)" }), wl, h("div", { class: "field" }, inp),
    h("p", { class: "meta", text: "Keywords stay on this device. They highlight matching stories; they never filter or hide anything." }));
  if (p.finance_on) {
    try {
      const b = await getJSON("data/latest.json");
      const all = [...b.stories, ...(b.pool || [])].filter((s) => s.category === "economy" || (s.tags || []).some((t) => ["economy", "business", "crypto"].includes(t)));
      v.append(h("div", { class: "label", text: "Today in finance" }));
      if (!all.length) v.append(h("div", { class: "empty", text: "No major financial story today." }));
      all.sort((a, b) => b.score - a.score).forEach((s) => v.append(storyCard(s, b.date, p.watchlist)));
    } catch { v.append(h("div", { class: "empty", text: "Brief unavailable." })); }
  }
  return v;
}

function yamlSnippet(c) {
  const days = c.custom.length ? c.custom : ["mon", "tue", "wed", "thu", "fri"];
  return `brief:\n  time: "${c.time}"\n  timezone: "${c.tz}"\n  frequency: ${c.freq}\n  custom_days: [${days.join(", ")}]\nalerts:\n  notify_levels: [${c.levels.join(", ")}]\nlocal_keywords: [${c.local.map((x) => JSON.stringify(x)).join(", ")}]\n`;
}
function repoInfo() {
  const m = location.hostname.match(/^([^.]+)\.github\.io$/);
  const repo = location.pathname.split("/")[1];
  return m && repo ? { owner: m[1], repo } : null;
}
async function viewSettings() {
  const p = prefs();
  const device = Intl.DateTimeFormat().resolvedOptions().timeZone;
  let server = null;
  try { server = (await getJSON("data/latest.json")); } catch { /* first run */ }
  const c = store.get("server", { time: "07:00", tz: server ? server.timezone : device, freq: "every_day", custom: ["mon", "tue", "wed", "thu", "fri"], levels: ["BREAKING"], local: [] });
  const v = h("div", null, h("header", { class: "masthead" }, h("div", { class: "eyebrow", text: "Preferences" }), h("h1", { text: "Settings" })));

  // MY INTERESTS
  const ic = h("div", { class: "chips" });
  const drawI = () => ic.replaceChildren(...INTERESTS.map((i) => h("button", { class: prefs().interests.includes(i.toLowerCase()) ? "on" : "", text: i,
    onclick: () => { const cur = new Set(prefs().interests); cur.has(i.toLowerCase()) ? cur.delete(i.toLowerCase()) : cur.add(i.toLowerCase()); store.set("interests", [...cur]); drawI(); } })));
  drawI();
  v.append(h("div", { class: "label", text: "My interests" }), ic,
    h("div", { class: "card" }, h("div", { class: "toggle" }, h("span", null, "Personalize order", h("small", { text: "Nudges your topics up. Must-know stories are always kept and 2 slots are reserved for pure importance — no filter bubble." }),),
      h("input", { type: "checkbox", class: "sw", checked: p.personalize, onchange: (e) => store.set("personalize", e.target.checked) }))));

  // SCHEDULE
  const snippet = h("pre", { class: "code" });
  const draw = () => { snippet.textContent = yamlSnippet(c); store.set("server", c); };
  const tzList = (Intl.supportedValuesOf ? Intl.supportedValuesOf("timeZone") : [device]);
  const tzSel = h("select", { onchange: (e) => { c.tz = e.target.value; draw(); } }, ...[...new Set([c.tz, device, ...tzList])].map((z) => h("option", { value: z, selected: z === c.tz, text: z + (z === device ? "  (this device)" : "") })));
  const freq = h("select", { onchange: (e) => { c.freq = e.target.value; dayBox.style.display = c.freq === "custom" ? "" : "none"; draw(); } },
    ...[["every_day", "Every day"], ["weekdays", "Weekdays"], ["custom", "Custom"]].map(([k, t]) => h("option", { value: k, selected: k === c.freq, text: t })));
  const dayBox = h("div", { class: "chips field" }, ...DAYS.map((d) => h("button", { class: c.custom.includes(d) ? "on" : "", text: d.toUpperCase(),
    onclick: (e) => { c.custom = c.custom.includes(d) ? c.custom.filter((x) => x !== d) : [...c.custom, d]; e.target.classList.toggle("on"); draw(); } })));
  dayBox.style.display = c.freq === "custom" ? "" : "none";
  const urgent = h("input", { type: "checkbox", class: "sw", checked: c.levels.includes("URGENT"), onchange: (e) => { c.levels = e.target.checked ? ["BREAKING", "URGENT"] : ["BREAKING"]; draw(); } });
  const local = h("input", { type: "text", value: c.local.join(", "), placeholder: "e.g. Miami, Florida", onchange: (e) => { c.local = e.target.value.split(",").map((x) => x.trim()).filter(Boolean); draw(); } });
  const info = repoInfo();
  const editUrl = info ? `https://github.com/${info.owner}/${info.repo}/edit/main/config/settings.yaml` : null;
  v.append(h("div", { class: "label", text: "Morning brief schedule" }),
    h("div", { class: "card" },
      h("div", { class: "field" }, h("label", { text: "Morning Brief Time" }), h("input", { type: "time", value: c.time, onchange: (e) => { c.time = e.target.value || "07:00"; draw(); } })),
      h("div", { class: "field" }, h("label", { text: `Timezone (device: ${device})` }), tzSel),
      h("div", { class: "field" }, h("label", { text: "Frequency" }), freq), dayBox,
      h("div", { class: "toggle" }, h("span", null, "Also alert on URGENT", h("small", { text: "Default: only BREAKING news interrupts you (max 3/day)." })), urgent),
      h("div", { class: "field" }, h("label", { text: "Local news keywords" }), local)),
    h("p", { class: "meta", text: "For security this app holds no credentials, so it cannot write to your server. Schedule settings live in one versioned file in your repo: paste this into config/settings.yaml (merge with existing keys) and commit. The next 30-minute tick picks it up." }),
    snippet,
    h("div", { class: "btnrow" }, h("button", { class: "btn", text: "Copy", onclick: async (e) => { try { await navigator.clipboard.writeText(yamlSnippet(c)); e.target.textContent = "Copied ✓"; } catch { /* ignore */ } } }),
      editUrl && ext(editUrl, "btn primary", "Open settings.yaml ↗")));
  draw();

  // NOTIFICATIONS
  const perm = "Notification" in window ? Notification.permission : "unsupported";
  v.append(h("div", { class: "label", text: "Notifications" }),
    h("div", { class: "card" },
      h("p", { class: "lead", text: "Push to your phone (works with the app closed): install the free ntfy app (iPhone or Android) and subscribe to the private topic you created during setup — see the README. Tapping ☀️ MORNING BRIEF READY or 🚨 BREAKING opens this app." }),
      h("div", { class: "toggle" }, h("span", null, "In-app alerts while open", h("small", { text: `Permission: ${perm}. Shows a notice when a new brief lands while the app is open.` })),
        h("button", { class: "btn ghost", text: "Enable", onclick: async () => { if ("Notification" in window) { await Notification.requestPermission(); route(); } } }))));

  // APPEARANCE + DATA
  v.append(h("div", { class: "label", text: "Appearance & data" }), h("div", { class: "card" },
    h("div", { class: "field" }, h("label", { text: "Theme" }), h("select", { onchange: (e) => { store.set("theme", e.target.value); applyTheme(); } },
      ...[["dark", "Dark"], ["light", "Light"], ["auto", "Automatic"]].map(([k, t]) => h("option", { value: k, selected: k === p.theme, text: t })))),
    h("div", { class: "toggle" }, h("span", null, "Reading memory", h("small", { text: `Stored only on this device. Categories opened: ${Object.entries(p.mem.cat).map(([k, n]) => k + " " + n).join(", ") || "none yet"}.` })),
      h("button", { class: "btn ghost", text: "Clear", onclick: () => { store.set("mem", { cat: {}, opened: {} }); route(); } }))));
  try {
    const hl = await getJSON("data/health.json");
    v.append(h("p", { class: "meta", text: `Last run: ${hl.feeds_ok}/${hl.feeds_total} feeds OK, ${hl.items} items from ${hl.sources_with_items.length} sources.` }));
  } catch { /* none */ }
  return v;
}

/* ---------- new-brief notice while the app is open ---------- */
async function checkNew(brief) {
  const seen = store.get("seen", null);
  if (seen && seen !== brief.generated_at && "Notification" in window && Notification.permission === "granted") {
    try {
      const reg = await navigator.serviceWorker.getRegistration();
      const opts = { body: `${brief.stories.length} things you should know today.`, icon: "icons/icon-192.png", data: { url: "./#/today" } };
      reg ? reg.showNotification("☀️ MORNING BRIEF READY", opts) : new Notification("☀️ MORNING BRIEF READY", opts);
    } catch { /* ignore */ }
  }
  store.set("seen", brief.generated_at);
}

/* ---------- router ---------- */
let lastTab = "today";
async function route() {
  const hash = location.hash.replace(/^#\/?/, "") || "today";
  const [name, a, b] = hash.split("/");
  if (["today", "history", "search", "finance", "settings"].includes(name)) lastTab = name;
  else if (name === "day") lastTab = "history";
  else if (name === "story" && a === "latest") lastTab = "today";   // otherwise keep the tab the user came from
  document.querySelectorAll("#tabs a").forEach((t) => t.classList.toggle("on", t.dataset.tab === lastTab));
  try {
    let view;
    if (name === "today") view = await viewToday();
    else if (name === "history") view = await viewHistory();
    else if (name === "day") view = await viewDay(a);
    else if (name === "story") view = b ? await viewStory(a, b) : await viewStory("latest", a);
    else if (name === "search") view = await viewSearch();
    else if (name === "finance") view = await viewFinance();
    else if (name === "niche") view = await viewNiche(a);
    else if (name === "settings") view = await viewSettings();
    else view = await viewToday();
    $app.replaceChildren(view);
  } catch (e) {
    $app.replaceChildren(h("div", { class: "empty" }, h("p", { text: "No brief available yet." }), h("p", { class: "meta", text: name === "today" ? "The first brief appears after the first scheduled run. Open Settings to review your schedule." : String(e.message) })));
    if (name === "today") $app.append(h("div", { class: "btnrow" }, h("a", { class: "btn", href: "#/settings", text: "Settings" })));
  }
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);
document.addEventListener("visibilitychange", () => { if (!document.hidden && (location.hash === "" || location.hash === "#/today")) route(); });
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
applyTheme();
route();
if ("serviceWorker" in navigator) addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
