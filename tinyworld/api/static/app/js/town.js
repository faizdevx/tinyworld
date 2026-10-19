// The Town: the living world from above. Tiles stream in as the map grows; people walk real
// paths; residents bring petitions to a podium; a paper comes out each day. Canvas 2D, no libraries.
import { api, listen } from "./api.js";
import { action, el, fill, setCrumbs, shortId, tag, toast, when } from "./ui.js";

const TERRAIN = {
  ".": "#6d7d4f", "=": "#b3a37f", "~": "#3f74ad", "#": "#4b4137", ",": "#d2c3a4", "+": "#8a5a2b", '"': "#a1ad50",
};
const STATE = {
  walking: "#4f8fe0", praying: "#e0b640", sleeping: "#8b8f98", talking: "#58b36b", idle: "#f2f0ea",
};
const POWERS = ["grant", "whisper", "sign", "refuse", "punish", "ignore"];
const CHUNK = 32;

function hourOf(iso) {
  const m = /T(\d\d):(\d\d)/.exec(iso || "");
  return m ? Number(m[1]) + Number(m[2]) / 60 : 12;
}

function night(hour) {
  if (hour >= 22 || hour < 5) return 0.5;
  if (hour >= 20) return 0.25;
  if (hour < 7) return 0.25;
  return 0;
}

export async function showTown(view, branchId) {
  setCrumbs([["Worlds", "#/"], ["Town", null]]);
  const world = {
    chunks: new Map(), places: {}, people: [], holy: [], unexplored: [], time: "", running: false,
    selected: null, scale: 7, cx: 0, cy: 0, follow: true, frames: null, frameAt: null, shown: new Map(),
  };

  window.townDebug = world; // for looking at the state from the console
  // -- layout ---------------------------------------------------------------
  const canvas = el("canvas", { class: "town-canvas", tabindex: 0 });
  const clock = el("span", { class: "muted" }, "");
  const playBtn = action("Play", async () => {
    if (world.running) await api(`/town/${branchId}/pause`, { method: "POST" });
    else await api(`/town/${branchId}/play`, { method: "POST" });
    world.running = !world.running;
    playBtn.textContent = world.running ? "Pause" : "Play";
  }, { class: "primary" });
  const jump = (label, minutes) =>
    action(label, async () => { await api(`/town/${branchId}/run`, { method: "POST", body: { minutes } }); await refresh(); }, { class: "ghost" });
  const scrub = el("input", { type: "range", min: 0, max: 100, value: 100, class: "town-scrub", "aria-label": "Timeline" });
  const scrubLabel = el("span", { class: "muted small" }, "now");
  const panel = el("div", { class: "town-panel" });
  const tabs = el("div", { class: "tabs" });
  const body = el("div", { class: "town-body" });
  const bar = el("div", { class: "row town-bar" },
    playBtn, jump("+10 min", 10), jump("+1 h", 60), jump("+6 h", 360), clock,
    el("label", { class: "small" }, el("input", { type: "checkbox", checked: true, onchange: (e) => { world.follow = e.target.checked; } }), " follow"),
    scrub, scrubLabel);
  view.append(el("div", { class: "town" }, el("div", { class: "town-map" }, bar, el("div", { class: "town-stage" }, canvas)), panel));
  panel.append(tabs, body);

  const ctx = canvas.getContext("2d");
  function resize() {
    const box = canvas.getBoundingClientRect();
    canvas.width = Math.max(300, Math.floor(box.width));
    canvas.height = Math.max(300, Math.floor(box.height));
  }
  new ResizeObserver(resize).observe(canvas);

  // -- data ---------------------------------------------------------------
  function takeSnapshot(s) {
    world.chunks = new Map(s.chunks.map((c) => [c.key, c]));
    world.places = s.places; world.holy = s.holy; world.unexplored = s.unexplored;
    world.time = s.time; world.running = s.running;
    playBtn.textContent = world.running ? "Pause" : "Play";
    setPeople(s.people);
    world.papers = s.papers; world.petitions = s.petitions;
    if (!world.start) { world.start = s.time; centre(); }
    draw(); renderTab();
  }
  function setPeople(people) {
    const now = performance.now();
    for (const p of people) {
      const old = world.shown.get(p.id);
      if (p.x == null) continue;
      world.shown.set(p.id, { from: old ? { x: old.x, y: old.y } : { x: p.x, y: p.y }, x: p.x, y: p.y, t: now });
    }
    world.people = people;
  }
  function centre() {
    const spots = world.people.filter((p) => p.x != null);
    if (!spots.length) return;
    world.cx = spots.reduce((a, p) => a + p.x, 0) / spots.length;
    world.cy = spots.reduce((a, p) => a + p.y, 0) / spots.length;
  }
  async function refresh() {
    takeSnapshot(await api(`/town/${branchId}`));
  }

  const stop = listen(`/ws/town/${branchId}`, (m) => {
    if (m.type === "snapshot") takeSnapshot(m);
    else if (m.type === "chunk.upsert") { world.chunks.set(m.chunk.key, m.chunk); toast("New ground opens up."); }
    else if (m.type === "position") {
      world.time = m.time; setPeople(m.people);
      if (world.follow && world.selected) {
        const p = world.people.find((q) => q.id === world.selected);
        if (p && p.x != null) { world.cx += (p.x - world.cx) * 0.4; world.cy += (p.y - world.cy) * 0.4; }
      }
      if (tab === "follow" && world.selected && Date.now() - lastFollow > 2500) renderTab();
    } else if (m.type === "petition") { world.petitions = m.open; if (tab === "petitions") renderTab(); badge(); }
    else if (m.type === "edition.add") { toast(`The paper is out: ${m.headline}`); refreshPapers(); }
  });

  // -- drawing ---------------------------------------------------------------
  const tx = (x) => (x - world.cx) * world.scale + canvas.width / 2;
  const ty = (y) => (y - world.cy) * world.scale + canvas.height / 2;

  function drawChunk(c) {
    const s = world.scale;
    const x0 = tx(c.cx * CHUNK), y0 = ty(c.cy * CHUNK);
    if (x0 > canvas.width || y0 > canvas.height || x0 + CHUNK * s < 0 || y0 + CHUNK * s < 0) return;
    for (let i = 0; i < c.terrain.length; i++) {
      const colour = TERRAIN[c.terrain[i]];
      ctx.fillStyle = colour;
      ctx.fillRect(x0 + (i % CHUNK) * s, y0 + Math.floor(i / CHUNK) * s, Math.ceil(s), Math.ceil(s));
    }
  }
  function drawFog() {
    ctx.fillStyle = "rgba(10,12,16,.55)";
    ctx.strokeStyle = "rgba(255,255,255,.18)";
    ctx.setLineDash([4, 4]);
    for (const key of world.unexplored) {
      const [cx, cy] = key.split(",").map(Number);
      if (world.chunks.has(key)) continue;
      const x = tx(cx * CHUNK), y = ty(cy * CHUNK), w = CHUNK * world.scale;
      ctx.fillRect(x, y, w, w); ctx.strokeRect(x, y, w, w);
      if (world.scale >= 6) { ctx.fillStyle = "rgba(255,255,255,.4)"; ctx.fillText("?", x + w / 2 - 3, y + w / 2 + 4); ctx.fillStyle = "rgba(10,12,16,.55)"; }
    }
    ctx.setLineDash([]);
  }
  function drawLabels() {
    if (world.scale < 5) return;
    ctx.font = `${Math.min(13, 6 + world.scale * 0.5)}px system-ui`;
    ctx.textAlign = "center";
    for (const c of world.chunks.values()) {
      for (const r of c.regions) {
        const place = world.places[r.place];
        if (!place || r.x0 < c.cx * CHUNK || r.y0 < c.cy * CHUNK) continue; // label once, in its first chunk
        const x = tx((r.x0 + r.x1 + 1) / 2), y = ty(r.y0) - 3;
        ctx.fillStyle = "rgba(0,0,0,.55)";
        const w = ctx.measureText(place.name).width + 6;
        ctx.fillRect(x - w / 2, y - 11, w, 14);
        ctx.fillStyle = world.holy.includes(r.place) ? "#f3d27a" : "#f4f1e8";
        ctx.fillText(place.name, x, y);
      }
    }
    ctx.textAlign = "start";
  }
  function position(p, now) {
    const shown = world.shown.get(p.id);
    if (!shown) return [p.x, p.y];
    const k = Math.min(1, (now - shown.t) / 380);
    return [shown.from.x + (shown.x - shown.from.x) * k, shown.from.y + (shown.y - shown.from.y) * k];
  }
  function drawPeople(now) {
    const list = world.frames && world.frameAt != null
      ? world.frames[world.frameAt].people.map((p) => ({ ...p, x: p.at ? p.at[0] : null, y: p.at ? p.at[1] : null, state: "idle" }))
      : world.people;
    const s = world.scale;
    for (const p of list) {
      if (p.x == null) continue;
      const [x, y] = world.frames ? [p.x, p.y] : position(p, now);
      const px = tx(x) + s / 2, py = ty(y) + s / 2;
      const r = Math.max(3.5, s * (p.child ? 0.4 : 0.62));
      ctx.fillStyle = "rgba(0,0,0,.3)"; ctx.beginPath(); ctx.ellipse(px, py + r * 0.9, r, r * 0.4, 0, 0, 7); ctx.fill();
      ctx.fillStyle = STATE[p.state] || STATE.idle; ctx.strokeStyle = "#1b1a17"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(px, py, r, 0, 7); ctx.fill(); ctx.stroke();
      if (p.id === world.selected) { ctx.strokeStyle = "#ffcf40"; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(px, py, r + 3, 0, 7); ctx.stroke(); }
      if (p.state === "talking") { ctx.fillStyle = "#fff"; ctx.fillText("…", px + r, py - r); }
      if (p.state === "praying") { ctx.fillStyle = "#ffe08a"; ctx.fillText("✦", px + r, py - r); }
      if (world.scale >= 8 || p.id === world.selected) {
        ctx.font = "11px system-ui"; ctx.fillStyle = "#fff"; ctx.strokeStyle = "rgba(0,0,0,.7)"; ctx.lineWidth = 3;
        ctx.strokeText(p.name, px - ctx.measureText(p.name).width / 2, py - r - 4);
        ctx.fillText(p.name, px - ctx.measureText(p.name).width / 2, py - r - 4);
      }
    }
  }
  function draw() {
    const now = performance.now();
    ctx.fillStyle = "#14161a"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    for (const c of world.chunks.values()) drawChunk(c);
    drawFog();
    drawLabels();
    drawPeople(now);
    const dark = night(hourOf(world.frames && world.frameAt != null ? world.frames[world.frameAt].time : world.time));
    if (dark) { ctx.fillStyle = `rgba(8,12,40,${dark})`; ctx.fillRect(0, 0, canvas.width, canvas.height); }
    clock.textContent = when(world.frames && world.frameAt != null ? world.frames[world.frameAt].time : world.time);
    requestAnimationFrame(() => { if (alive) draw(); });
  }
  let alive = true;

  // -- pointer: pan, zoom, pick --------------------------------------------------
  let drag = null;
  canvas.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, cx: world.cx, cy: world.cy, moved: false }; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true;
    world.cx = drag.cx - dx / world.scale; world.cy = drag.cy - dy / world.scale;
  });
  canvas.addEventListener("pointerup", (e) => {
    if (drag && !drag.moved) pick(e);
    drag = null;
  });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    world.scale = Math.max(2, Math.min(28, world.scale * (e.deltaY < 0 ? 1.15 : 0.87)));
  }, { passive: false });
  function pick(e) {
    const box = canvas.getBoundingClientRect();
    const x = (e.clientX - box.left - canvas.width / 2) / world.scale + world.cx - 0.5;
    const y = (e.clientY - box.top - canvas.height / 2) / world.scale + world.cy - 0.5;
    let best = null, bestD = 2.2;
    for (const p of world.people) {
      if (p.x == null) continue;
      const d = Math.hypot(p.x - x, p.y - y);
      if (d < bestD) { best = p; bestD = d; }
    }
    if (best) select(best.id);
  }
  function select(id) { world.selected = id; setTab("follow"); }

  // -- timeline ------------------------------------------------------------------
  scrub.addEventListener("change", async () => {
    if (Number(scrub.value) >= 100) { world.frames = null; world.frameAt = null; scrubLabel.textContent = "now"; return; }
    if (!world.start) return;
    const a = new Date(world.start), b = new Date(world.time);
    const total = (b - a) / 60000;
    if (total < 30) return;
    if (!world.frames) {
      const iso = (d) => d.toISOString().slice(0, 19);
      world.frames = await api(`/town/${branchId}/timeline?start=${iso(a)}&end=${iso(b)}&step=${Math.max(10, Math.ceil(total / 300))}`);
    }
    world.frameAt = Math.round((Number(scrub.value) / 100) * (world.frames.length - 1));
    scrubLabel.textContent = "looking back";
  });
  scrub.addEventListener("input", () => { if (world.frames) { world.frameAt = Math.round((Number(scrub.value) / 100) * (world.frames.length - 1)); } });

  // -- the side panels -------------------------------------------------------------
  let tab = "follow", lastFollow = 0;
  const names = [["follow", "Follow"], ["petitions", "Petitions"], ["paper", "Paper"], ["talk", "Talk"], ["graphs", "Graphs"], ["worlds", "Many worlds"]];
  function setTab(t) { tab = t; renderTab(); }
  function badge() {
    for (const b of tabs.children) if (b.dataset.t === "petitions") b.textContent = `Petitions${world.petitions && world.petitions.length ? ` (${world.petitions.length})` : ""}`;
  }
  fill(tabs, ...names.map(([t, label]) => el("button", { class: "tab", "data-t": t, onclick: () => setTab(t) }, label)));
  async function refreshPapers() { world.papers = await api(`/town/${branchId}/papers`); if (tab === "paper") renderTab(); }

  async function renderTab() {
    for (const b of tabs.children) b.setAttribute("aria-selected", b.dataset.t === tab ? "true" : "false");
    badge();
    if (tab === "follow") return renderFollow();
    if (tab === "petitions") return renderPetitions();
    if (tab === "paper") return renderPaper();
    if (tab === "talk") return renderTalk();
    if (tab === "graphs") return renderGraphs();
    if (tab === "worlds") return renderWorlds();
  }

  async function renderFollow() {
    if (!world.selected) return fill(body, el("p", { class: "muted" }, "Click a person on the map to follow them."));
    lastFollow = Date.now();
    const f = await api(`/town/${branchId}/follow/${world.selected}`);
    const bars = Object.entries(f.drives).map(([name, d]) =>
      el("div", { class: "row small" }, el("span", { style: "width:78px" }, name),
        el("div", { class: "bar" }, el("div", { class: "bar-fill", style: `width:${d.level}%;${d.level < d.set - 15 ? "background:var(--bad)" : ""}` })),
        el("span", { class: "muted" }, `${d.level}/${d.set}`)));
    fill(body,
      el("h3", {}, f.name), el("div", { class: "muted small" }, `${f.occupation || "resident"} · ${f.place}`),
      el("p", {}, f.doing || "…"),
      f.thought ? el("p", { class: "muted" }, `“${f.thought}”`) : null,
      el("h2", {}, "Plan"), el("ol", { class: "small" }, ...(f.plan.length ? f.plan : ["(none yet)"]).map((s) => el("li", {}, s))),
      el("h2", {}, `Wants · frustration ${Math.round(f.frustration * 100)}%`), ...bars,
      el("div", { class: "row small" }, tag(`faith ${f.faith}`), f.walking_to ? tag(`on the way to ${shortId(f.walking_to)}`, "warn") : null,
        f.petition ? tag("has a petition", "warn") : null),
      el("h2", {}, "Remembers"), el("ul", { class: "small" }, ...f.memories.map((m) => el("li", {}, m))),
      el("div", { class: "muted small" }, "To see why something happened, open Graphs and enter its event number."));
  }

  async function renderPetitions() {
    const list = world.petitions || [];
    if (!list.length) return fill(body, el("p", { class: "muted" }, "Nobody is asking for anything. Residents come to a shrine when they need to."));
    fill(body, ...list.map((p) => {
      const text = el("input", { placeholder: "your words, or what to do (e.g. give her three loaves)", "aria-label": "Answer" });
      return el("div", { class: "panel stack" },
        el("div", { class: "row" }, el("strong", {}, p.name), tag(p.kind)),
        el("p", {}, p.text), p.offering ? el("div", { class: "muted small" }, `offers: ${p.offering}`) : null,
        text,
        el("div", { class: "row" }, ...POWERS.map((power) => action(power, async () => {
          const bodyJson = power === "grant" || power === "punish" ? { power, command: text.value } : { power, text: text.value };
          try { await api(`/town/${branchId}/petitions/${p.id}/answer`, { method: "POST", body: bodyJson }); toast(`${p.name}: ${power}.`); await refresh(); }
          catch (error) { toast(error.message); }
        }, { class: power === "ignore" ? "ghost" : "" }))));
    }));
  }

  async function renderPaper() {
    const papers = await api(`/town/${branchId}/papers`);
    if (!papers.length) return fill(body, el("p", { class: "muted" }, "The first paper comes out when a day has ended."));
    fill(body, ...papers.map((p) => el("details", {}, el("summary", {}, `${p.day} — ${p.headline}`),
      el("pre", { class: "small", style: "white-space:pre-wrap" }, p.text))));
  }

  async function renderTalk() {
    if (!world.selected) return fill(body, el("p", { class: "muted" }, "Pick someone on the map, then ask them something."));
    const person = world.people.find((p) => p.id === world.selected);
    const question = el("input", { placeholder: "Ask them anything", "aria-label": "Question" });
    const appear = el("input", { type: "checkbox" });
    const log = el("div", { class: "stack" });
    const ask = action("Ask", async () => {
      const q = question.value.trim(); if (!q) return;
      const r = await api(`/town/${branchId}/interview`, { method: "POST", body: { person: world.selected, question: q, appear: appear.checked } });
      log.append(el("p", {}, el("em", {}, q)), el("p", {}, `${person ? person.name : "They"}: ${r.answer}`));
      question.value = "";
    }, { class: "primary" });
    fill(body, el("h3", {}, `Talk to ${person ? person.name : "them"}`),
      el("p", { class: "muted small" }, "They answer from their own memories and change nothing, unless you appear to them."),
      question, el("label", { class: "small" }, appear, " appear to them as the god"), ask, log);
  }

  async function renderGraphs() {
    const [rel, rum] = await Promise.all([api(`/town/${branchId}/graph/relationships`), api(`/town/${branchId}/graph/rumours`)]);
    const g = el("canvas", { width: 330, height: 330, class: "town-graph" });
    const c = g.getContext("2d");
    const pos = new Map(rel.nodes.map((n, i) => [n.id, [165 + 135 * Math.cos((2 * Math.PI * i) / rel.nodes.length), 165 + 135 * Math.sin((2 * Math.PI * i) / rel.nodes.length)]]));
    for (const e of rel.edges) {
      const a = pos.get(e.from), b = pos.get(e.to); if (!a || !b) continue;
      c.strokeStyle = e.value >= 0 ? `rgba(80,180,120,${Math.min(1, Math.abs(e.value) / 80)})` : `rgba(210,80,70,${Math.min(1, Math.abs(e.value) / 80)})`;
      c.lineWidth = 1 + Math.abs(e.value) / 40; c.beginPath(); c.moveTo(...a); c.lineTo(...b); c.stroke();
    }
    for (const n of rel.nodes) {
      const [x, y] = pos.get(n.id); c.fillStyle = "#ddd"; c.beginPath(); c.arc(x, y, 5, 0, 7); c.fill();
      c.fillStyle = "#999"; c.font = "10px system-ui"; c.fillText(n.name.split(" ")[0], x - 12, y - 8);
    }
    const seq = el("input", { type: "number", placeholder: "event number", "aria-label": "Event number" });
    const why = el("ul", { class: "small" });
    fill(body, el("h2", {}, "Who likes whom (green warm, red cold)"), g,
      el("h2", {}, "Who told whom"),
      el("ul", { class: "small" }, ...rum.edges.slice(-8).map((e) => el("li", {}, `${shortId(e.from)} → ${shortId(e.to)}: ${e.text}`))),
      el("h2", {}, "Why did it happen?"), el("div", { class: "row" }, seq, action("Trace", async () => {
        const w = await api(`/town/${branchId}/why/${seq.value}`);
        fill(why, ...w.nodes.map((n) => el("li", {}, `${n.seq}: ${n.narration}`)));
      }, { class: "ghost" })), why);
  }

  async function renderWorlds() {
    const runs = el("input", { type: "number", value: 5, min: 2, max: 50, "aria-label": "Runs" });
    const hours = el("input", { type: "number", value: 24, min: 1, max: 240, "aria-label": "Hours" });
    const out = el("div", { class: "stack" });
    const go = action("Run it", async () => {
      const { job } = await api(`/town/${branchId}/multiverse`, { method: "POST", body: { runs: Number(runs.value), hours: Number(hours.value) } });
      fill(out, el("p", { class: "muted" }, "Running…"));
      for (;;) {
        await new Promise((r) => setTimeout(r, 1500));
        const j = await api(`/town/multiverse/${job}`);
        if (j.status === "running") continue;
        if (j.status === "error") return fill(out, el("p", {}, j.error));
        const sp = j.spread;
        fill(out,
          el("div", { class: "muted small" }, `story spread ${sp.headline.story_spread} · outcome spread ${sp.headline.outcome_spread}`),
          el("h2", {}, "In how many runs it held"),
          ...sp.contested.slice(0, 24).map((k) => {
            const v = k.startsWith("alive:") ? sp.alive[k.slice(6)] : k.startsWith("place:") ? sp.places[k.slice(6)] : sp.events[k];
            return el("div", { class: "row small" }, el("span", { style: "flex:1" }, k.replace(/^(\w+):.*?:/, "$1 ").slice(0, 46)),
              el("div", { class: "bar", style: "width:90px;flex:none" }, el("div", { class: "bar-fill", style: `width:${Math.round(v * 100)}%` })), el("span", {}, `${Math.round(v * 100)}%`));
          }),
          el("h2", {}, "Open one"), el("div", { class: "row" }, ...j.branches.map((b) => el("a", { class: "button ghost", href: `#/town/${b.branch_id}` }, `run ${b.index + 1}`))));
        return;
      }
    }, { class: "primary" });
    fill(body, el("h3", {}, "Run it many times"),
      el("p", { class: "muted small" }, "Fork this world and let each copy live on its own luck. See what changes, and how often."),
      el("div", { class: "row" }, runs, " runs ", hours, " hours "), go, out);
  }

  await refresh();
  setTab("follow");
  return () => { alive = false; stop(); };
}
